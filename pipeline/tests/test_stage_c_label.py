"""T07 验收测试：阶段 C 封闭打标 + 两个闸门 + 降级（**全离线**）。

用一个「假子进程 runner」驱动**真实**的 ``DshHeadlessClient.run_batch``，因此
批量切分、L0 重试、L1 修复式重试、L2 二分拆批、``attempts`` 计数全部走真实代码路径，
只有 ``node`` 调用被换掉 —— 不联网、不调 LLM。

覆盖验收点：
* 全量可用评论逐条打标；每条 label 带 ``evidence``（英文原文）+ ``dimension_name``（中文名）；
* ``labeling.ok`` 每条必填，``ok=false`` 带 ``error``；
* 闸门① pilot ``other`` 占比 > 15%（**分母仅 ok=true**）→ 立即中止；
* 闸门② 失败率 > 10%（**分母 = 已发标条数**）→ 立即中止；
* **三个分母口径不同、未被统一**（PRD §8.4 / 验收 §10.3）；
* 二分拆批 + ``attempts`` 生效；枚举越界 / 缺 evidence 被拒。
"""

from __future__ import annotations

import json

import pytest

from tableware_radar import config
from tableware_radar.aggregate import aggregate
from tableware_radar.dimensions import load_dimension_set
from tableware_radar.llm.client import DshHeadlessClient
from tableware_radar.models import Label, ReviewRecord
from tableware_radar.stage_c_label import (
    ERR_GATE_ABORT,
    ERR_UNUSABLE,
    GATE_FAILURE_OVER_10PCT,
    GATE_OTHER_OVER_15PCT,
    StageCLabeler,
    build_partial_analysis,
    evaluate_gates,
    is_other_record,
)

# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #

_DIM_NAME = {"DUR": "耐用性", "PCK": "包装", "SAF": "合规/安全", "OTHER": "其他"}


def _dims():
    return load_dimension_set(config.DIMENSIONS_PATH)


def _label(dimension: str, value: str, polarity: str = "neg") -> Label:
    return Label(
        dimension=dimension,
        dimension_name=_DIM_NAME.get(dimension, dimension),
        value=value,
        polarity=polarity,
        confidence=0.8,
        evidence="a small chip appeared on the rim",
    )


def _rec(
    review_id: str,
    asin: str = "A",
    *,
    usable: bool = True,
    labels: list[Label] | None = None,
    sent: bool | None = None,
    ok: bool | None = None,
    error: str = "",
    text: str | None = None,
) -> ReviewRecord:
    """造一条清洗后的记录；``sent``/``ok`` 给定即视为「已打标」。"""
    record = ReviewRecord(
        review_id=review_id,
        asin=asin,
        source={"url": f"https://x/dp/{asin}", "fetcher_version": "0.1.0"},
        raw={"title": "Sturdy plates", "body": "Sturdy plates", "rating": 4, "review_date": "2026-01-01"},
        content={"text": text if text is not None else ("sturdy plates that survived the dishwasher " * 3),
                 "is_usable": usable},
        labels=list(labels or []),
        labeling={"ok": False, "error": "pending_labeling", "attempts": 0},
    )
    if sent is not None or ok is not None:
        record.labeling = {"ok": bool(ok), "error": error, "sent": bool(sent), "attempts": 1}
    return record


# ---- 假子进程：从 task 里反查 review_id，按策略生成 stdout ----
#
# 必须只解析 INPUT REVIEWS 那段 JSON —— prompt 里的 EXAMPLE OUTPUT 与修复重试里附回
# 的上一版输出都带 "review_id"，用裸正则会把它们一起捞进来，假 runner 就会多吐一条。

_INPUT_ANCHOR = "INPUT REVIEWS ("


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


def _stdout(ids: list[str], *, other=(), evidence: str = "a small chip appeared on the rim",
            dimension: str = "DUR", value: str = "chips_easily",
            name: str | None = None) -> str:
    """为给定 review_id 生成一份**合规**的阶段 C 输出。"""
    other_set = set(other)
    items = []
    for rid in ids:
        if rid in other_set:
            labels = [{
                "dimension": "OTHER", "dimension_name": "其他", "value": "odd smell",
                "polarity": "neg", "confidence": 0.4, "evidence": "it had an odd smell",
            }]
        else:
            labels = [{
                "dimension": dimension,
                "dimension_name": name if name is not None else _DIM_NAME.get(dimension, dimension),
                "value": value, "polarity": "neg", "confidence": 0.8, "evidence": evidence,
            }]
        items.append({"review_id": rid, "labels": labels})
    return json.dumps(items, ensure_ascii=False)


class Runner:
    """可脚本化的假 runner（签名与 ``DshHeadlessClient`` 期望的一致）。"""

    def __init__(self, policy):
        self.policy = policy
        self.calls: list[list[str]] = []

    def __call__(self, task, timeout):  # noqa: ANN001 - runner 协议
        ids = _ids_in(task)
        self.calls.append(ids)
        return self.policy(ids, task, self)

    @property
    def sent_ids(self) -> list[str]:
        return [rid for call in self.calls for rid in call]


def _client(runner: Runner, **kwargs) -> DshHeadlessClient:
    kwargs.setdefault("max_retries", 0)
    return DshHeadlessClient(runner=runner, **kwargs)


def _ok_policy(ids, task, self):  # noqa: ANN001
    return 0, _stdout(ids), ""


# --------------------------------------------------------------------------- #
# 逐条打标 / 字段完整性
# --------------------------------------------------------------------------- #

def test_labels_every_usable_record_and_skips_unusable():
    dims = _dims()
    records = [_rec(f"R{i}") for i in range(5)] + [_rec("U1", usable=False, text="ok")]
    runner = Runner(_ok_policy)

    result = StageCLabeler(_client(runner), dims, batch_size=3, pilot_size=3).run(records)

    assert result.aborted is False
    assert result.stats.labeled_ok == 5
    assert result.stats.labeled_failed == 0
    assert result.stats.skipped_unusable == 1
    assert all(r.labeling_ok for r in records[:5])
    # 不可用记录**不送标**，且不留 pending 态
    assert records[5].labeling["ok"] is False
    assert records[5].labeling["error"] == ERR_UNUSABLE
    assert records[5].labeling["sent"] is False
    assert "U1" not in runner.sent_ids


def test_every_label_carries_evidence_and_chinese_name():
    dims = _dims()
    records = [_rec(f"R{i}") for i in range(4)]
    StageCLabeler(_client(Runner(_ok_policy)), dims, pilot_size=2).run(records)

    for record in records:
        assert record.labels, "每条可用记录都应有 label"
        for label in record.labels:
            assert label.evidence                      # 英文原文
            assert label.dimension_name                # 中文显示名
            assert label.dimension_name == "耐用性"
            assert label.value == "chips_easily"       # 枚举保持英文下划线
            assert record.labeling["ok"] is True


def test_evidence_is_kept_verbatim_and_not_translated():
    dims = _dims()
    records = [_rec("R1")]
    evidence = "one plate chipped after a few washes"
    runner = Runner(lambda ids, task, self: (0, _stdout(ids, evidence=evidence), ""))
    StageCLabeler(_client(runner), dims, pilot_size=1).run(records)
    assert records[0].labels[0].evidence == evidence


def test_dimension_name_is_corrected_from_dimensions_yaml():
    """LLM 抄错中文名无所谓 —— 真源是 dimensions.yaml。"""
    dims = _dims()
    records = [_rec("R1")]
    runner = Runner(lambda ids, task, self: (0, _stdout(ids, name="WRONG NAME"), ""))
    StageCLabeler(_client(runner), dims, pilot_size=1).run(records)
    assert records[0].labels[0].dimension_name == "耐用性"
    assert records[0].labeling_ok is True


def test_labeling_metadata_is_recorded():
    dims = _dims()
    records = [_rec("R1")]
    StageCLabeler(_client(Runner(_ok_policy)), dims, pilot_size=1, model_name="stub-model").run(records)
    labeling = records[0].labeling
    assert labeling["prompt_version"].startswith("prompt-")
    assert labeling["dimension_set_version"] == dims.version
    assert labeling["model"] == "stub-model"
    assert labeling["labels_count"] == 1
    assert labeling["attempts"] == 1


# --------------------------------------------------------------------------- #
# 校验 / 修复 / 降级
# --------------------------------------------------------------------------- #

def test_missing_evidence_is_rejected_with_reason():
    dims = _dims()
    records = [_rec("R1"), _rec("R2")]
    bad = json.dumps(
        [{"review_id": rid, "labels": [{"dimension": "DUR", "dimension_name": "耐用性",
                                        "value": "chips_easily", "polarity": "neg", "confidence": 0.5}]}
         for rid in ("R1", "R2")],
        ensure_ascii=False,
    )
    runner = Runner(lambda ids, task, self: (0, bad, ""))

    result = StageCLabeler(_client(runner), dims, pilot_size=2, batch_size=2).run(records)

    assert all(r.labeling_ok is False for r in records)
    assert all("evidence" in r.labeling["error"] for r in records)
    assert result.gate == GATE_FAILURE_OVER_10PCT          # 100% 失败


def test_out_of_enum_value_is_rejected_with_reason():
    dims = _dims()
    records = [_rec("R1")]
    bad = _stdout(["R1"], value="makes_coffee")             # 不在 DUR 枚举内
    runner = Runner(lambda ids, task, self: (0, bad, ""))

    result = StageCLabeler(_client(runner), dims, pilot_size=1).run(records)

    assert records[0].labeling_ok is False
    assert "枚举" in records[0].labeling["error"]
    assert result.gate == GATE_FAILURE_OVER_10PCT


def test_repair_is_used_before_giving_up():
    """L1：第一次输出不合规 → 带 REJECTED 的修复 task 重试 → 成功。"""
    dims = _dims()
    records = [_rec("R1")]
    bad = json.dumps([{"review_id": "R1", "labels": [{"dimension": "DUR", "dimension_name": "耐用性",
                                                     "value": "chips_easily", "polarity": "neg",
                                                     "confidence": 0.5}]}], ensure_ascii=False)
    seen = {"repaired": 0}

    def policy(ids, task, self):  # noqa: ANN001
        if "REJECTED" in task:
            seen["repaired"] += 1
            return 0, _stdout(ids), ""
        return 0, bad, ""

    runner = Runner(policy)
    result = StageCLabeler(_client(runner, max_retries=1), dims, pilot_size=1).run(records)

    assert seen["repaired"] == 1
    assert records[0].labeling_ok is True
    assert records[0].labeling["attempts"] == 2          # attempts 真实反映重试
    assert result.gate is None


def test_binary_split_isolates_one_poison_record():
    """L2：整批失败时二分拆批，只有坏条目 ok=false，其余照常成功。"""
    dims = _dims()
    records = [_rec(f"R{i:02d}") for i in range(12)]

    def policy(ids, task, self):  # noqa: ANN001
        if "R05" in ids:
            return 1, "", "poison record"
        return 0, _stdout(ids), ""

    runner = Runner(policy)
    result = StageCLabeler(_client(runner), dims, pilot_size=12, batch_size=12).run(records)

    assert records[5].labeling_ok is False
    assert "poison" in records[5].labeling["error"]
    assert all(r.labeling_ok for i, r in enumerate(records) if i != 5)
    # 1/12 = 8.3% ≤ 10% → 不破线
    assert result.gate is None
    assert result.stats.labeled_ok == 11
    assert result.stats.labeled_failed == 1
    # 真的发生了二分（出现了小于整批的中间批次）
    assert any(len(ids) == 6 for ids in runner.calls)


def test_process_failure_is_reported_not_swallowed():
    dims = _dims()
    records = [_rec(f"R{i}") for i in range(3)]
    runner = Runner(lambda ids, task, self: (1, "", "dsh crashed"))

    result = StageCLabeler(_client(runner), dims, pilot_size=3, batch_size=3).run(records)

    assert all(r.labeling_ok is False for r in records)
    assert all(r.labeling["error"] for r in records)     # 有原因，不是空
    assert all(r.labeling["sent"] is True for r in records)
    assert result.gate == GATE_FAILURE_OVER_10PCT


# --------------------------------------------------------------------------- #
# 闸门① / 闸门② + 三个分母**未被统一**
# --------------------------------------------------------------------------- #

def test_gate_one_trips_on_pilot_other_share_over_15pct():
    dims = _dims()
    records = [_rec(f"R{i:02d}") for i in range(20)]
    others = {f"R{i:02d}" for i in range(6)}             # 6/20 = 30% > 15%
    runner = Runner(lambda ids, task, self: (0, _stdout(ids, other=others), ""))

    result = StageCLabeler(_client(runner), dims, pilot_size=20, batch_size=10).run(records)

    assert result.gate == GATE_OTHER_OVER_15PCT
    assert result.pilot.ok_records == 20                  # 分母 = ok=true
    assert result.pilot.other_records == 6
    assert abs(result.pilot.other_ratio - 0.30) < 1e-9
    assert result.pilot.failure_rate == 0.0
    assert result.full is None                            # pilot 就中止了


def test_gate_one_abort_does_not_spend_budget_on_the_rest():
    dims = _dims()
    records = [_rec(f"R{i:02d}") for i in range(30)]
    others = {f"R{i:02d}" for i in range(10)}            # pilot 内 10/20 = 50%
    runner = Runner(lambda ids, task, self: (0, _stdout(ids, other=others), ""))

    result = StageCLabeler(_client(runner), dims, pilot_size=20, batch_size=10).run(records)

    assert result.gate == GATE_OTHER_OVER_15PCT
    assert result.stats.pilot_records == 20
    assert result.stats.sent == 20                        # 只发了 pilot
    assert result.stats.not_labeled_gate_abort == 10
    assert len(runner.sent_ids) == 20
    # 未打标的记录显式标注「未送标」，不是 pending
    assert all(r.labeling["error"] == ERR_GATE_ABORT for r in records[20:])
    assert all(r.labeling["sent"] is False for r in records[20:])


def test_gate_two_trips_on_failure_rate_over_10pct():
    dims = _dims()
    records = [_rec(f"R{i:02d}") for i in range(10)]
    runner = Runner(lambda ids, task, self: (1, "", "dsh crashed"))

    result = StageCLabeler(_client(runner), dims, pilot_size=10, batch_size=10).run(records)

    assert result.gate == GATE_FAILURE_OVER_10PCT
    assert result.pilot.sent_records == 10                # 分母 = 已发标
    assert result.pilot.ok_records == 0
    assert result.pilot.failure_rate == 1.0


def test_three_denominators_are_not_unified():
    """★ PRD §8.4 / 验收 §10.3：造 ok=false 数据，coverage↓、other 占比**不变**、失败率↑。"""
    dims = _dims()
    records = [_rec(f"R{i:02d}", labels=[_label("DUR", "chips_easily")], sent=True, ok=True)
               for i in range(18)]
    records += [_rec(f"O{i}", labels=[_label("OTHER", "odd smell")], sent=True, ok=True)
                for i in range(2)]
    base = evaluate_gates(records)
    assert (base.ok_records, base.sent_records) == (20, 20)
    assert abs(base.other_ratio - 2 / 20) < 1e-9           # 10% < 15%
    assert base.failure_rate == 0.0
    assert base.gate is None

    # 追加 3 条 ok=false（都已发标）
    records += [_rec(f"F{i}", labels=[], sent=True, ok=False, error="boom") for i in range(3)]
    ev = evaluate_gates(records)

    # 闸门① 分母只算 ok=true → other 占比**不变**
    assert abs(ev.other_ratio - 2 / 20) < 1e-9
    # 若有人把两个分母统一（都除以已发标），会得到 2/23 —— 必须不是
    assert abs(ev.other_ratio - 2 / 23) > 1e-9
    # 闸门② 分母 = 已发标 23 → 3/23 ≈ 13% > 10%
    assert abs(ev.failure_rate - 3 / 23) < 1e-9
    assert ev.gate == GATE_FAILURE_OVER_10PCT

    # labeled_coverage 分母含 ok=false → 20/23，确实下降
    analysis = aggregate(records, dims)
    assert abs(analysis.sample["labeled_coverage"] - 20 / 23) < 1e-6
    assert analysis.sample["comments_usable"] == 23


def test_gate_two_excludes_never_sent_records():
    """分母是「已发标」，不是 comments_usable —— 没发出去的条目不背这个锅。"""
    records = [_rec(f"R{i}", labels=[_label("DUR", "chips_easily")], sent=True, ok=True)
               for i in range(9)]
    records.append(_rec("F1", labels=[], sent=True, ok=False, error="boom"))
    ev = evaluate_gates(records)
    assert abs(ev.failure_rate - 0.10) < 1e-9
    assert ev.gate is None                                  # 恰好 10% 不破线（> 才破）

    for i in range(5):                                     # 5 条**未发标**（不可用/中止）
        records.append(_rec(f"U{i}", usable=False, sent=False, ok=False, error=ERR_UNUSABLE))
    ev2 = evaluate_gates(records)
    assert abs(ev2.failure_rate - 0.10) < 1e-9              # 分母不变
    assert ev2.gate is None


def test_is_other_record_semantics():
    assert is_other_record(_rec("X", labels=[_label("OTHER", "odd smell")])) is True
    assert is_other_record(_rec("X", labels=[_label("DUR", "chips_easily")])) is False
    # 有已定义维度 + 附带 OTHER → 标签体系确实放下了它，不算 other
    assert is_other_record(
        _rec("X", labels=[_label("DUR", "chips_easily"), _label("OTHER", "odd smell")])
    ) is False
    # labels=[] 是"成功打标但无命中"，也不是 other
    assert is_other_record(_rec("X", labels=[])) is False


def test_evaluate_gates_on_empty_input():
    ev = evaluate_gates([])
    assert ev.gate is None and ev.sent_records == 0 and ev.other_ratio == 0.0


# --------------------------------------------------------------------------- #
# partial analysis.json
# --------------------------------------------------------------------------- #

def test_build_partial_analysis_carries_the_gate():
    dims = _dims()
    records = [_rec(f"R{i:02d}", asin=f"A{i % 4}") for i in range(10)]
    others = {f"R{i:02d}" for i in range(5)}              # 50% > 15%
    runner = Runner(lambda ids, task, self: (0, _stdout(ids, other=others), ""))

    result = StageCLabeler(_client(runner), dims, pilot_size=10).run(records)
    assert result.gate == GATE_OTHER_OVER_15PCT

    analysis = build_partial_analysis(result, dims, generated_at="2026-01-01T00:00:00Z")
    assert analysis.data_quality["gate"] == GATE_OTHER_OVER_15PCT
    assert analysis.generated_at == "2026-01-01T00:00:00Z"
    assert analysis.dimension_set_version == dims.version


def test_clean_run_produces_no_gate():
    dims = _dims()
    records = [_rec(f"R{i:02d}", asin=f"A{i}") for i in range(8)]
    runner = Runner(lambda ids, task, self: (0, _stdout(ids, dimension="DUR"), ""))

    result = StageCLabeler(_client(runner), dims, pilot_size=4, batch_size=4).run(records)

    assert result.gate is None
    assert result.full is not None and result.full.gate is None
    analysis = build_partial_analysis(result, dims, generated_at="2026-01-01T00:00:00Z")
    assert analysis.data_quality["gate"] is None
    assert analysis.sample["labeled_coverage"] == 1.0


def test_empty_and_all_unusable_inputs_are_safe():
    dims = _dims()

    empty_runner = Runner(_ok_policy)
    empty = StageCLabeler(_client(empty_runner), dims).run([])
    assert empty.records == [] and empty.gate is None and empty.stats.sent == 0

    called: list[list[str]] = []
    runner = Runner(lambda ids, task, self: (called.append(ids), (0, "[]", ""))[1])
    records = [_rec("U1", usable=False, text="x"), _rec("U2", usable=False, text="y")]
    result = StageCLabeler(_client(runner), dims).run(records)

    assert called == []                                   # 一条都没发出去
    assert result.gate is None
    assert result.stats.skipped_unusable == 2
    assert result.stats.sent == 0


def test_empty_dimension_set_is_rejected():
    from tableware_radar.dimensions import DimensionSet

    with pytest.raises(ValueError):
        StageCLabeler(_client(Runner(_ok_policy)), DimensionSet(version="dims-v1"))
