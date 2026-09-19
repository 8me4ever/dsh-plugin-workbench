"""T02 验收测试：``DshHeadlessClient`` + ``PromptLibrary``（不依赖真实网络/LLM）。

覆盖（对应 ARCHITECTURE §5 T02 验收）：

* ``extract_json`` 对 fence / prose / 数组的健壮抽取；
* 超时 / 非零退出 / 坏 JSON 三类失败各有桩，``attempts`` 计数正确；
* L1 修复式重试（``validator`` + ``repair``）；
* ``run_batch`` 批次级二分拆批与单条失败隔离（不静默丢弃）；
* ``ensure_profile`` 环境缺失时快速失败并给出可复制修复命令；
* ``PromptLibrary`` 版本号、阶段 A「禁止归类」、阶段 C 封闭枚举渲染。
"""

from __future__ import annotations

import pytest

from tableware_radar.llm import (
    DshHeadlessClient,
    LlmEnvironmentError,
    LlmError,
    LlmParseError,
    LlmTimeoutError,
    PromptLibrary,
    extract_json,
    find_dsh_entry,
)
from tableware_radar.models import Dimension


# --------------------------------------------------------------------------- #
# extract_json
# --------------------------------------------------------------------------- #

def test_extract_json_plain_array():
    assert extract_json('[{"a": 1}]') == [{"a": 1}]


def test_extract_json_with_fence():
    assert extract_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]


def test_extract_json_with_surrounding_prose():
    text = 'Sure, here is the result:\n[{"a": 1}]\nHope this helps!'
    assert extract_json(text) == [{"a": 1}]


def test_extract_json_raises_on_garbage():
    with pytest.raises(LlmParseError):
        extract_json("no json here at all")
    with pytest.raises(LlmParseError):
        extract_json("")


# --------------------------------------------------------------------------- #
# Fake runner 工具
# --------------------------------------------------------------------------- #

class FakeRunner:
    """按脚本依次返回响应：元组 = (rc, stdout, stderr)；异常 = 抛出。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[tuple[str, float]] = []

    def __call__(self, task: str, timeout_s: float):
        self.calls.append((task, timeout_s))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_client(runner, **kwargs):
    return DshHeadlessClient(runner=runner, log_path=kwargs.pop("log_path", "/tmp/tr_test_labeling.log"), **kwargs)


# --------------------------------------------------------------------------- #
# run_json / attempts
# --------------------------------------------------------------------------- #

def test_run_json_success_first_try():
    client = make_client(FakeRunner([(0, '[{"ok": true}]', "dsh: reasoning: ...")]))
    assert client.run_json("task") == [{"ok": True}]
    assert client.last_attempts == 1


def test_run_json_retries_on_timeout_and_nonzero_then_succeeds():
    runner = FakeRunner([
        LlmTimeoutError("timeout"),
        (1, "", "boom"),
        (0, '[{"ok": true}]', ""),
    ])
    client = make_client(runner, max_retries=2)
    value, attempts = client.run_json_with_attempts("task")
    assert value == [{"ok": True}]
    assert attempts == 3                       # 两次失败 + 一次成功
    assert len(runner.calls) == 3


def test_run_json_exhausts_retries_and_raises():
    runner = FakeRunner([(1, "", "x"), (1, "", "x"), (1, "", "x")])
    client = make_client(runner, max_retries=2)
    with pytest.raises(LlmError):
        client.run_json("task")
    assert len(runner.calls) == 3              # max_attempts = retries + 1


def test_run_json_bad_json_triggers_retry():
    runner = FakeRunner([(0, "not json", ""), (0, '[1,2]', "")])
    client = make_client(runner, max_retries=1)
    assert client.run_json("task") == [1, 2]


# --------------------------------------------------------------------------- #
# L1 修复式重试
# --------------------------------------------------------------------------- #

def test_validator_failure_triggers_repair():
    runner = FakeRunner([(0, '[{"a": 1}]', ""), (0, '[{"a": 1, "b": 2}]', "")])

    def validator(value):
        assert value[0].get("b") is not None, "missing key b"

    repairs: list[tuple[str, str, str]] = []

    def repair(task, error, raw):
        repairs.append((task, error, raw))
        return task + " [REPAIR]"

    client = make_client(runner, max_retries=1)
    value = client.run_json("orig", validator=validator, repair=repair)
    assert value == [{"a": 1, "b": 2}]
    assert len(repairs) == 1
    assert runner.calls[1][0].endswith("[REPAIR]")   # repair 改写了 task


# --------------------------------------------------------------------------- #
# run_batch：二分拆批 + 失败隔离
# --------------------------------------------------------------------------- #

def _ok_runner_for_single():
    """整批（多条目，task 含逗号）失败；拆到单条后成功 —— 验证二分拆批。"""
    def runner(task: str, timeout_s: float):
        if "," in task:
            return (1, "", "batch failed")
        return (0, '[{"label": "x"}]', "")
    return runner


def test_run_batch_halves_on_failure():
    client = make_client(_ok_runner_for_single())
    results = client.run_batch(["A", "B"], build_prompt=lambda items: ",".join(items), batch_size=2)
    assert len(results) == 2
    assert all(r.ok for r in results)
    assert [r.index for r in results] == [0, 1]


def test_run_batch_isolates_persistent_failure():
    # 单条 "B" 永远失败 → 该条 ok=False，且 attempts 被记录（不静默丢弃）。
    def runner(task, timeout_s):
        if "B" in task:
            return (1, "", "boom")
        return (0, '[{"label": "x"}]', "")

    client = make_client(runner, max_retries=1)
    results = client.run_batch(["A", "B"], build_prompt=lambda items: ",".join(items), batch_size=2)
    by_index = {r.index: r for r in results}
    assert by_index[0].ok is True
    assert by_index[1].ok is False
    assert by_index[1].error
    assert by_index[1].attempts >= 1


def test_run_batch_on_item_callback():
    seen = []
    client = make_client(_ok_runner_for_single())
    client.run_batch(
        ["A"], build_prompt=lambda items: ",".join(items),
        batch_size=1, on_item=lambda r: seen.append(r.index),
    )
    assert seen == [0]


# --------------------------------------------------------------------------- #
# ensure_profile 环境失败
# --------------------------------------------------------------------------- #

def test_ensure_profile_failure_is_environment_error_with_hint():
    client = make_client(FakeRunner([LlmTimeoutError("cold start too slow")]))
    with pytest.raises(LlmEnvironmentError) as excinfo:
        client.ensure_profile(timeout_s=1)
    message = str(excinfo.value)
    assert "npm i -g @deepseek-ai/dsh" in message     # 可复制修复命令
    assert "headless" in message


def test_ensure_profile_success():
    client = make_client(FakeRunner([(0, "", "dsh: reasoning: warm")]))
    client.ensure_profile(timeout_s=1)                 # 不抛即通过


def test_find_dsh_entry_raises_when_absent(monkeypatch, tmp_path):
    import tableware_radar.llm.client as client_mod

    monkeypatch.setattr(client_mod.shutil, "which", lambda _name: None)
    monkeypatch.setenv("APPDATA", str(tmp_path / "nonexistent"))
    with pytest.raises(LlmEnvironmentError):
        find_dsh_entry()


# --------------------------------------------------------------------------- #
# PromptLibrary
# --------------------------------------------------------------------------- #

def test_prompt_library_version():
    lib = PromptLibrary()
    assert lib.prompt_version.startswith("prompt-")


def test_stage_a_forbids_categorization_and_is_json_contract():
    lib = PromptLibrary()
    task = lib.build_stage_a([{"review_id": "R1", "title": "t", "body": "b"}])
    assert "Do NOT classify" in task
    assert "json" in task.lower()
    assert "R1" in task
    assert task.count("[") >= 1


def test_stage_c_renders_closed_enumerations():
    lib = PromptLibrary()
    dims = [
        Dimension(id="DUR", name="耐用性", definition="耐用", values=["chips_easily", "durable_strong"]),
        Dimension(id="SAF", name="合规/安全", definition="安全", values=["lead_free_claim"], excluded_from_opportunity=True),
    ]
    task = lib.build_stage_c([{"review_id": "R1", "title": "t", "body": "b"}], dims)
    assert "DUR" in task and "SAF" in task
    assert "chips_easily" in task
    assert "耐用性" in task                      # 中文显示名
    assert "evidence" in task
    assert "Do NOT invent dimensions" in task


def test_build_repair_mentions_reason_and_originals():
    lib = PromptLibrary()
    task = lib.build_repair("c", [{"review_id": "R1", "title": "t", "body": "b"}], "missing evidence", "prev", dimensions=[])
    assert "missing evidence" in task
    assert "REJECTION REASON" in task
