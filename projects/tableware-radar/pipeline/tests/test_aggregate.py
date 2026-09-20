"""T08 验收测试：聚合打分（纯离线）。

覆盖：rankable 三阈值（可配置）、opportunities/selection_priority 仅含 rankable 且 SCN/SAF
排除、selection_priority ≤7、risk_flags(SAF)、filters(SCN)、by_asin.opportunity、
labeled_coverage 分母含 ok=false、采样偏差披露、可复现（同输入同输出）、无候选款字段。
"""

from __future__ import annotations

from tableware_radar import config
from tableware_radar.aggregate import Aggregator, aggregate
from tableware_radar.dimensions import load_dimension_set
from tableware_radar.models import FetchReport, Label, ReviewRecord


def _label(dimension: str, value: str, polarity: str, evidence: str = "ev") -> Label:
    return Label(dimension=dimension, dimension_name=dimension, value=value,
                 polarity=polarity, confidence=0.9, evidence=evidence)


def _rec(review_id, asin, labels, *, usable=True, ok=True, rating=5, date="2026-01-01"):
    return ReviewRecord(
        review_id=review_id,
        asin=asin,
        source={"url": f"https://x/dp/{asin}", "fetcher_version": "0.1.0"},
        raw={"rating": rating, "review_date": date},
        content={"text": "x" * 50 if usable else "ok", "is_usable": usable},
        labels=labels,
        labeling={"ok": ok, "attempts": 1},
    )


def _dataset():
    dims = load_dimension_set(config.DIMENSIONS_PATH)
    records = [
        _rec("R1", "A", [_label("DUR", "chips_easily", "neg")]),
        _rec("R2", "A", [_label("DUR", "cracks_easily", "neg")]),
        _rec("R3", "A", [_label("SCN", "everyday_dining", "neutral")]),
        _rec("R4", "A", [_label("SAF", "lead_free_claim", "neutral")]),
        _rec("R5", "B", [_label("DUR", "chips_easily", "neg")]),
        _rec("R6", "B", [_label("DUR", "chips_easily", "neg")]),
        _rec("R7", "B", [_label("PCK", "arrived_damaged", "neg")]),
        _rec("R8", "B", [_label("SCN", "everyday_dining", "neutral")]),
        _rec("R9", "C", [_label("DUR", "chips_easily", "neg")]),
        _rec("R10", "C", [_label("DUR", "scratches_easily", "neg")]),
        _rec("R11", "C", [_label("OTHER", "delivery packaging", "neg")]),
        _rec("R12", "C", [_label("DUR", "chips_easily", "neg")], ok=False),   # 打标失败
        _rec("R13", "D", [], usable=False),                                    # 不可用
    ]
    reports = [
        FetchReport(asin="A", requested=100, fetched=13, ok=True, fetcher_version="0.1.0"),
        FetchReport(asin="B", requested=100, fetched=6, ok=False, fetcher_version="0.1.0"),
        FetchReport(asin="C", requested=100, fetched=13, ok=True, fetcher_version="0.1.0"),
    ]
    return records, dims, reports


# --------------------------------------------------------------------------- #
# rankable / 维度级
# --------------------------------------------------------------------------- #

def test_rankable_uses_configurable_thresholds():
    records, dims, reports = _dataset()
    analysis = aggregate(records, dims, reports=reports)
    dims_out = {d["id"]: d for d in analysis.dimensions}

    dur = dims_out["DUR"]
    assert dur["hits"] == 6
    assert dur["asin_count"] == 3
    assert dur["rankable"] is True
    assert dur["low_confidence"] is False

    pck = dims_out["PCK"]
    assert pck["hits"] == 1
    assert pck["rankable"] is False
    assert pck["low_confidence"] is True         # 恒互补


def test_rankable_threshold_scales_with_asin_count():
    # 4 个 ASIN → 阈值 = max(3, ceil(0.3*4)=2) = 3；这里命中仅 1 个 ASIN → 不可 rankable
    records = [
        _rec("R1", "A", [_label("DUR", "chips_easily", "neg")]),
        _rec("R2", "A", [_label("DUR", "chips_easily", "neg")]),
        _rec("R3", "A", [_label("DUR", "chips_easily", "neg")]),
        _rec("R4", "B", []),
        _rec("R5", "C", []),
        _rec("R6", "D", []),
    ]
    dims = load_dimension_set(config.DIMENSIONS_PATH)
    analysis = aggregate(records, dims)
    dur = {d["id"]: d for d in analysis.dimensions}["DUR"]
    assert dur["hits"] == 3
    assert dur["asin_count"] == 1
    assert dur["rankable"] is False              # 命中集中在一个商品，护栏生效


def test_custom_thresholds_via_constructor():
    agg = Aggregator(hits_min=1, asin_ratio=0.0, asin_floor=1)
    assert agg.rankable(hits=1, asin_count=1, asins_with_data=10) is True
    assert Aggregator(hits_min=3, asin_ratio=0.3, asin_floor=2).rankable(2, 3, 10) is False


# --------------------------------------------------------------------------- #
# 口径：SCN/SAF 排除、selection_priority ≤7、opportunities 仅 rankable
# --------------------------------------------------------------------------- #

def test_scn_saf_excluded_from_opportunities():
    records, dims, reports = _dataset()
    analysis = aggregate(records, dims, reports=reports)
    opp_dims = {o["dimension"] for o in analysis.opportunities}
    assert "DUR" in opp_dims
    assert "SCN" not in opp_dims
    assert "SAF" not in opp_dims
    for o in analysis.opportunities:
        assert o["dimension"] not in {"SCN", "SAF"}


def test_opportunities_only_rankable():
    records, dims, reports = _dataset()
    analysis = aggregate(records, dims, reports=reports)
    # PCK 命中 1（< HITS_MIN）→ 不入 opportunities
    assert "PCK" not in {o["dimension"] for o in analysis.opportunities}


def test_selection_priority_length_cap():
    records, dims, reports = _dataset()
    analysis = aggregate(records, dims, reports=reports)
    assert len(analysis.selection_priority) <= 7


def test_risk_flags_and_filters():
    records, dims, reports = _dataset()
    analysis = aggregate(records, dims, reports=reports)
    assert any(f["dimension"] == "SAF" and f["value"] == "lead_free_claim" for f in analysis.risk_flags)
    assert analysis.filters.get("everyday_dining") == 2
    # filters 覆盖全部 SCN 枚举键
    scn = dims.get("SCN")
    for value in scn.values:
        assert value in analysis.filters


# --------------------------------------------------------------------------- #
# by_asin / sample / data_quality
# --------------------------------------------------------------------------- #

def test_by_asin_has_opportunity_sorted_desc():
    records, dims, reports = _dataset()
    analysis = aggregate(records, dims, reports=reports)
    assert len(analysis.by_asin) == 3
    opps = [a["opportunity"] for a in analysis.by_asin]
    assert opps == sorted(opps, reverse=True)
    assert all("opportunity" in a for a in analysis.by_asin)


def test_labeled_coverage_denominator_includes_ok_false():
    records, dims, reports = _dataset()
    analysis = aggregate(records, dims, reports=reports)
    sample = analysis.sample
    assert sample["comments_usable"] == 12          # R1..R12（R13 不可用）
    assert sample["asins_with_data"] == 3           # A/B/C（D 不可用）
    # labeled_coverage = 成功打标 / usable = 11 / 12（分母含 1 条 ok=false）
    assert abs(sample["labeled_coverage"] - 11 / 12) < 1e-6
    assert analysis.data_quality["labeling_failures"] == 1
    assert analysis.data_quality["skipped_unusable"] == 1


def test_data_quality_sampling_bias_and_underfilled():
    records, dims, reports = _dataset()
    analysis = aggregate(records, dims, reports=reports)
    dq = analysis.data_quality
    assert dq["sampling_bias"]["source"] == "amazon_top_reviews"
    assert "complaint_dims_overestimated" in dq["sampling_bias"]["effects"]
    assert {"asin": "B", "fetched": 6} in dq["underfilled_asins"]
    assert "B" in dq["failed_asins"]
    # low_confidence_dimensions 带未达标原因
    reasons = {d["id"]: d["reason"] for d in dq["low_confidence_dimensions"]}
    assert reasons.get("PCK") == "hits_below_min"


def test_other_topics_aggregated():
    records, dims, reports = _dataset()
    analysis = aggregate(records, dims, reports=reports)
    assert {"topic_phrase": "delivery packaging", "count": 1} in analysis.other_topics


# --------------------------------------------------------------------------- #
# 可复现 & 边界
# --------------------------------------------------------------------------- #

def test_deterministic_same_input_same_output():
    records, dims, reports = _dataset()
    a = aggregate(records, dims, reports=reports, generated_at="2026-01-01T00:00:00Z").to_dict()
    b = aggregate(records, dims, reports=reports, generated_at="2026-01-01T00:00:00Z").to_dict()
    assert a == b


def test_no_candidate_fields():
    records, dims, reports = _dataset()
    analysis = aggregate(records, dims, reports=reports).to_dict()
    assert not any("candidate" in k.lower() for k in analysis)


def test_empty_input_is_safe():
    dims = load_dimension_set(config.DIMENSIONS_PATH)
    analysis = aggregate([], dims)
    assert analysis.opportunities == []
    assert analysis.sample["comments_usable"] == 0
    assert analysis.sample["labeled_coverage"] == 0.0


# --------------------------------------------------------------------------- #
# 定稿口径回归（PRD §4.4 / §7.4）—— 这三条在旧实现下会红
# --------------------------------------------------------------------------- #

def test_asin_floor_default_is_three():
    """PRD §4.4 定稿：asin_count_min = 3（v1.2 的 >=2 已作废）。"""
    assert config.RANKABLE_ASIN_FLOOR == 3
    assert config.rankable_asin_threshold(9) == 3      # max(3, ceil(2.7)=3)
    assert config.rankable_asin_threshold(30) == 9     # max(3, ceil(9)=9)：比例项接管，无需改代码


def test_satisfaction_follows_prd_definition():
    """PRD §4.4：satisfaction = (net_sat + 1)/2，分母是 hits（含 other 极性）。"""
    assert Aggregator.satisfaction(pos=0, neg=4, hits=4) == 0.0     # 全负
    assert Aggregator.satisfaction(pos=2, neg=2, hits=4) == 0.5     # 平衡
    # pos=2 / other=2：net_sat = 2/4 = 0.5 → satisfaction = 0.75
    assert abs(Aggregator.satisfaction(pos=2, neg=0, hits=4) - 0.75) < 1e-9
    # 旧的 pos/(pos+neg) 会给出 1.0 —— 必须不等，证明用的是 PRD 定义
    assert abs(Aggregator.satisfaction(pos=2, neg=0, hits=4) - 1.0) > 1e-9
    assert Aggregator.satisfaction(pos=0, neg=0, hits=0) == 0.5     # 回退


def test_asin_opportunity_is_category_weight_times_local_neg_share():
    """PRD §7.4：Σ opportunity(d) × neg_share(d,a)；不是 per-ASIN attention×(1−sat)。"""
    # 直接验证乘积语义
    pairs = [(0.5, 1.0), (0.2, 0.5)]
    assert abs(Aggregator.asin_opportunity(pairs) - (0.5 * 1.0 + 0.2 * 0.5)) < 1e-9
    assert abs(Aggregator.asin_opportunity([(0.9, 0.0)]) - 0.0) < 1e-9   # hits==0 维不贡献

    # 端到端：A 的 DUR 命中 2 条且全为负 → neg_share=1.0
    #   ⇒ asin_opportunity(A) 应恰好等于维度级 opportunity(DUR)
    records, dims, reports = _dataset()
    analysis = aggregate(records, dims, reports=reports)
    dur_opp = {o["dimension"]: o["opportunity"] for o in analysis.opportunities}["DUR"]
    by_asin = {a["asin"]: a for a in analysis.by_asin}
    assert abs(by_asin["A"]["opportunity"] - dur_opp) < 1e-6
    # 旧口径对 A 会得到 per-ASIN attention(2/4=0.5)×(1−0)=0.5，与维度级量明显不等
    assert abs(by_asin["A"]["opportunity"] - 0.5) > 1e-6
