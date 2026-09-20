"""T09 验收测试：端到端编排 CLI（**全离线、零等待**）。

用一个「假子进程 runner」驱动**真实**的 ``DshHeadlessClient``，并用 ``FixtureFetcher``
提供确定性假数据；通过 ``main`` 的注入缝（``fetcher`` / ``client`` / ``paths`` /
``sleeper`` / ``jitter``）把整条链路跑到离线，不联网、不调 LLM、不等待。

覆盖验收点（ARCHITECTURE §5 T09）：
* ``run --all`` 一条命令跑通 抓取→清洗→A→C→聚合，产出 ``analysis.json``；
* ``dimensions.yaml`` **不存在** → 提示「复制 dimensions.example.yaml」并给可复制命令；
* ``dimensions.yaml`` **存在但 validate() 不过** → 拒绝执行；
* **任一步失败**都打印可复制修复命令；
* 闸门破线 → 落 partial ``analysis.json``（带 ``gate``）+ 非零退出。
"""

from __future__ import annotations

import json

import pytest

from tableware_radar import config
from tableware_radar.cli import PipelinePaths, build_parser, main
from tableware_radar.fetch import FixtureFetcher
from tableware_radar.llm.client import DshHeadlessClient
from tableware_radar.models import FetchReport

# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #

_ASINS = ("B000000001", "B000000002")

_INPUT_ANCHOR = "INPUT REVIEWS ("
_STAGE_A_MARK = "OPEN CODING"
_STAGE_C_MARK = "CLOSED-CODE LABELING"


def _no_sleep(*_args, **_kwargs) -> None:
    return None


def _no_jitter(low, _high):  # noqa: ANN001
    return low


def _ids_in(task: str) -> list[str]:
    anchor = task.find(_INPUT_ANCHOR)
    if anchor < 0:
        return []
    start = task.find("[", anchor)
    if start < 0:
        return []
    try:
        items, _end = json.JSONDecoder().raw_decode(task[start:])
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    return [str(item.get("review_id", "")) for item in items if isinstance(item, dict)]


def _stage_a_out(ids: list[str]) -> str:
    items = [
        {"claim_text": f"plates chip after washing ({rid})", "topic_phrase": "durability",
         "sentiment": "neg", "source_review_id": rid}
        for rid in ids
    ]
    return json.dumps(items, ensure_ascii=False)


def _stage_c_out(ids: list[str], *, other: bool = False) -> str:
    items = []
    for rid in ids:
        if other:
            labels = [{"dimension": "OTHER", "dimension_name": "其他", "value": "odd smell",
                       "polarity": "neg", "confidence": 0.4, "evidence": "it had an odd smell"}]
        else:
            labels = [{"dimension": "DUR", "dimension_name": "耐用性", "value": "chips_easily",
                       "polarity": "neg", "confidence": 0.8,
                       "evidence": "a small chip appeared on the rim"}]
        items.append({"review_id": rid, "labels": labels})
    return json.dumps(items, ensure_ascii=False)


class _StubFetcher:
    """始终返回给定错误的抓取器（覆盖「抓取失败要报对病因」）。"""

    version = "stub"

    def __init__(self, error: str) -> None:
        self.error = error

    def fetch_reviews(self, asin, limit):  # noqa: ANN001
        report = FetchReport(
            asin=asin, requested=limit, fetched=0, platform_cap=13, ok=False,
            attempts=1, fetcher_version=self.version, error=self.error,
        )
        return [], report


class Runner:
    """可脚本化的假 runner；按 prompt 里的标记区分阶段 A / 阶段 C。"""

    def __init__(self, policy):
        self.policy = policy
        self.calls: list[list[str]] = []

    def __call__(self, task, timeout):  # noqa: ANN001
        ids = _ids_in(task)
        self.calls.append(ids)
        return self.policy(ids, task, self)


def _ok_policy(ids, task, self):  # noqa: ANN001
    if _STAGE_A_MARK in task:
        return 0, _stage_a_out(ids), ""
    if _STAGE_C_MARK in task:
        return 0, _stage_c_out(ids), ""
    return 0, "ok", ""                       # 暖机 "ok"


def _client(policy) -> DshHeadlessClient:
    return DshHeadlessClient(runner=Runner(policy), max_retries=0)


def _paths(tmp_path) -> PipelinePaths:
    return PipelinePaths(
        raw_dir=tmp_path / "raw",
        fetch_report_file=tmp_path / "raw" / "fetch_report.json",
        clean_file=tmp_path / "clean" / "reviews.jsonl",
        topics_file=tmp_path / "topics" / "raw_topics.jsonl",
        labeled_file=tmp_path / "labeled" / "labeled.jsonl",
        analysis_file=tmp_path / "analysis.json",
    )


def _run(argv, tmp_path, policy=_ok_policy, **kwargs):
    kwargs.setdefault("fetcher", FixtureFetcher(asins=_ASINS))
    kwargs.setdefault("client", _client(policy))
    kwargs.setdefault("paths", _paths(tmp_path))
    kwargs.setdefault("asins", _ASINS)
    kwargs.setdefault("sleeper", _no_sleep)
    kwargs.setdefault("jitter", _no_jitter)
    kwargs.setdefault("generated_at", "2026-01-01T00:00:00Z")
    return main(argv, **kwargs)


# --------------------------------------------------------------------------- #
# run --all 全链路
# --------------------------------------------------------------------------- #

def test_run_all_completes_end_to_end(tmp_path, capsys):
    rc = _run(["run", "--all"], tmp_path)

    out = capsys.readouterr().out
    assert rc == 0, out
    assert "[完成]" in out

    paths = _paths(tmp_path)
    # 全链路各步产物都在
    assert paths.fetch_report_file.exists()
    assert paths.clean_file.exists()
    assert paths.topics_file.exists()
    assert paths.labeled_file.exists()
    assert paths.analysis_file.exists()

    report = json.loads(paths.fetch_report_file.read_text(encoding="utf-8"))
    assert report["summary"]["slots"] == 2

    data = json.loads(paths.analysis_file.read_text(encoding="utf-8"))
    assert data["data_quality"]["gate"] is None
    assert len(data["by_asin"]) == 2
    assert data["sample"]["comments_usable"] > 0
    assert data["dimension_set_version"] == "dims-v1"


def test_run_defaults_to_all(tmp_path, capsys):
    """``run`` 不带任何 flag 也应等于 ``run --all``。"""
    rc = _run(["run"], tmp_path)
    assert rc == 0
    assert _paths(tmp_path).analysis_file.exists()


def test_topics_file_has_stage_a_schema(tmp_path):
    _run(["run", "--all"], tmp_path)
    lines = _paths(tmp_path).topics_file.read_text(encoding="utf-8").splitlines()
    topics = [json.loads(line) for line in lines]
    # 2 ASIN × 每 ASIN 抽 10
    assert len(topics) == 20
    for topic in topics:
        assert set(topic.keys()) == {"claim_text", "topic_phrase", "sentiment", "source_review_id"}


def test_only_fetch_stops_before_aggregate(tmp_path, capsys):
    rc = _run(["run", "--only", "fetch"], tmp_path)
    assert rc == 0
    paths = _paths(tmp_path)
    assert paths.fetch_report_file.exists()
    assert not paths.analysis_file.exists()          # 没跑到聚合
    assert not paths.topics_file.exists()


# --------------------------------------------------------------------------- #
# 前置检查：dimensions.yaml
# --------------------------------------------------------------------------- #

def test_missing_dimensions_yaml_fails_with_copy_command(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "nope" / "dimensions.yaml"
    monkeypatch.setattr(config, "DIMENSIONS_PATH", missing)

    rc = _run(["run", "--all"], tmp_path)

    out = capsys.readouterr().out
    assert rc == 2
    assert "dimensions.example.yaml" in out            # 提示以示例为起点
    assert "copy" in out                                # 给出可复制命令
    assert str(missing) in out


def test_invalid_dimensions_yaml_is_refused(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "dimensions.yaml"
    bad.write_text("version: dims-v1\ndimensions: []\n", encoding="utf-8")  # 空枚举 → validate 拒
    monkeypatch.setattr(config, "DIMENSIONS_PATH", bad)

    rc = _run(["run", "--all"], tmp_path)

    out = capsys.readouterr().out
    assert rc == 2
    assert "校验未通过" in out
    assert "copy" in out
    assert not _paths(tmp_path).analysis_file.exists()


# --------------------------------------------------------------------------- #
# 步骤失败 → 可复制修复命令
# --------------------------------------------------------------------------- #

def test_stage_failure_prints_copyable_fix_command(tmp_path, capsys):
    def failing_policy(ids, task, self):  # noqa: ANN001
        if _STAGE_A_MARK in task:
            return 1, "", "boom"            # 阶段 A 批次全失败
        if _STAGE_C_MARK in task:
            return 0, _stage_c_out(ids), ""
        return 0, "ok", ""                   # 暖机通过，确保失败点落在阶段 A

    rc = _run(["run", "--all"], tmp_path, policy=failing_policy)

    out = capsys.readouterr().out
    assert rc == 1
    assert "[失败]" in out
    assert "可复制执行的修复命令" in out
    assert "python -m tableware_radar.cli" in out or "npm i -g" in out


def test_gate_trip_writes_partial_analysis_and_exits_nonzero(tmp_path, capsys):
    def other_policy(ids, task, self):  # noqa: ANN001
        if _STAGE_A_MARK in task:
            return 0, _stage_a_out(ids), ""
        if _STAGE_C_MARK in task:
            return 0, _stage_c_out(ids, other=True), ""   # 全落 OTHER → 闸门① 破线
        return 0, "ok", ""

    rc = _run(["run", "--all"], tmp_path, policy=other_policy)

    out = capsys.readouterr().out
    assert rc == 1
    assert "闸门" in out and "阶段 B" in out

    paths = _paths(tmp_path)
    assert paths.analysis_file.exists()                   # partial analysis 已落盘
    data = json.loads(paths.analysis_file.read_text(encoding="utf-8"))
    assert data["data_quality"]["gate"] == "other_over_15pct"


def test_fetch_dependency_missing_reports_real_fix(tmp_path, capsys):
    """缺 scrapling → 必须给 pip 命令，而不是误导去查网络/ASIN。"""
    fetcher = _StubFetcher("fetch_failed: ModuleNotFoundError: No module named 'scrapling'")
    rc = _run(["run", "--all"], tmp_path, fetcher=fetcher)

    out = capsys.readouterr().out
    assert rc == 1
    assert "scrapling" in out                                   # 原文透传，病因可见
    assert "pip install -r pipeline/requirements.txt" in out    # 真正能修好的命令
    assert "run --only fetch" not in out                        # 不是网络分支
    assert "asins.txt" not in out


def test_fetch_network_failure_keeps_network_branch(tmp_path, capsys):
    fetcher = _StubFetcher("fetch_failed: ConnectionError: timed out")
    rc = _run(["run", "--all"], tmp_path, fetcher=fetcher)

    out = capsys.readouterr().out
    assert rc == 1
    assert "ConnectionError" in out                             # per-ASIN 错误原文透传
    assert "asins.txt" in out                                   # 网络/ASIN 分支
    assert "pip install" not in out


# --------------------------------------------------------------------------- #
# CLI 结构
# --------------------------------------------------------------------------- #

def test_parser_has_run_and_doctor():
    parser = build_parser()
    args = parser.parse_args(["run", "--only", "c"])
    assert args.command == "run" and args.only == "c"
    assert parser.parse_args(["doctor"]).command == "doctor"
    assert parser.parse_args(["run", "--all"]).all is True


def test_doctor_reports_environment(capsys):
    rc = main(["doctor"])
    out = capsys.readouterr().out
    assert "[doctor]" in out
    assert "scrapling" in out          # 依赖自检：缺失时不得谎报就绪（真抓取硬依赖）
    assert rc in (0, 1)
