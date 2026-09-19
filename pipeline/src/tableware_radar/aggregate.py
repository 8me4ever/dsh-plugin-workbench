"""聚合打分 → ``analysis.json``（docs/ARCHITECTURE.md §3.2 / §5 T08）。

公式（PRD §4.4）：

* ``attention(d)``          = 提及 d 的可用记录数 / 可用记录数（提及率）
* ``net_sat(d)``            = (pos − neg) / hits
* ``satisfaction(d)``       = (net_sat(d) + 1) / 2 ∈ [0,1]（``hits`` 为 0 时回退 0.5）★ PRD §4.4
* ``opportunity(d)``        = attention(d) × (1 − satisfaction(d))   ← 维度级、全样本算
* ``asin_opportunity(a)``   = Σ_{d ∈ rankable 评分维} ( opportunity(d) × neg_share(d, a) )  ★ PRD §7.4
* ``neg_share(d, a)``       = neg(d,a) / hits(d,a)（``hits`` 为 0 时该项贡献 0）
* ``rankable(d)``           = hits ≥ HITS_MIN 且 asin_count ≥ max(FLOOR, ceil(RATIO × asins_with_data))

口径硬约束（§7）：

* **``rankable`` 三阈值全部取自 config，禁硬编码**（R7；扩到 30 ASIN 不改代码）。
* ``SCN`` 只进 ``filters``、``SAF`` 只进 ``risk_flags``，二者**不入** ``opportunities[]`` /
  ``selection_priority[]``。
* ``opportunities[]`` / ``selection_priority[]`` **仅含 rankable 维度**；``selection_priority``
  长度 **≤ 7**。
* ``low_confidence ≡ !rankable``（恒互补），并带未达标 ``reason``。
* ``labeled_coverage`` 分母 = ``comments_usable``（**含 ok=false**）；``other`` 占比分母只算
  ``ok=true`` —— **两者口径不同，禁止统一**（此处只产 ``labeled_coverage``）。
* **不含任何候选款字段**（PRD §9.1）。
* 纯函数：**同输入同输出**（可复现）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from . import config
from .dimensions import EXCLUDED_FROM_OPPORTUNITY_IDS, OTHER_DIMENSION_ID, DimensionSet
from .models import Analysis, Label, ReviewRecord

__all__ = ["Aggregator", "aggregate"]


# 采样偏差披露（§7 ★ / R9）——固定文案。
_SAMPLING_BIAS = {
    "source": "amazon_top_reviews",
    "effects": ["complaint_dims_overestimated", "casual_mention_dims_underestimated"],
    "note": "广度可消除商品个性偏差；消除不了精选方法论的系统性偏差",
}


def _bucket(polarity: str) -> str:
    pol = (polarity or "").lower()
    if pol == "pos":
        return "pos"
    if pol == "neg":
        return "neg"
    return "other"


@dataclass
class _DimStat:
    """单维度的中间统计。"""

    dim_id: str
    hits: int = 0
    pos: int = 0
    neg: int = 0
    other: int = 0
    asins: set[str] = field(default_factory=set)
    evidence_pos: list[tuple[str, str, str]] = field(default_factory=list)  # (quote, review_id, asin)
    evidence_neg: list[tuple[str, str, str]] = field(default_factory=list)
    value_counts: dict[str, int] = field(default_factory=dict)

    def register(self, label: Label, record: ReviewRecord) -> None:
        self.hits += 1
        bucket = _bucket(label.polarity)
        if bucket == "pos":
            self.pos += 1
        elif bucket == "neg":
            self.neg += 1
        else:
            self.other += 1
        self.asins.add(record.asin)
        self.value_counts[label.value] = self.value_counts.get(label.value, 0) + 1
        if label.evidence:
            item = (label.evidence, record.review_id, record.asin)
            if bucket == "neg":
                self.evidence_neg.append(item)
            else:
                self.evidence_pos.append(item)


class Aggregator:
    """把打标后的 ``ReviewRecord`` 聚合为 ``Analysis``。"""

    def __init__(
        self,
        *,
        hits_min: Optional[int] = None,
        asin_ratio: Optional[float] = None,
        asin_floor: Optional[int] = None,
        matrix_top_asins: Optional[int] = None,
        top_evidence_n: int = 3,
    ) -> None:
        self.hits_min = hits_min if hits_min is not None else config.RANKABLE_HITS_MIN
        self.asin_ratio = asin_ratio if asin_ratio is not None else config.RANKABLE_ASIN_RATIO
        self.asin_floor = asin_floor if asin_floor is not None else config.RANKABLE_ASIN_FLOOR
        self.matrix_top_asins = (
            matrix_top_asins if matrix_top_asins is not None else config.MATRIX_TOP_ASINS
        )
        self.top_evidence_n = top_evidence_n

    # ------------------------------------------------------------------ #
    # 基础指标（对齐类图签名）
    # ------------------------------------------------------------------ #
    def rankable(self, hits: int, asin_count: int, asins_with_data: int) -> bool:
        """``rankable`` 判定（三阈值取自实例/config，非硬编码）。"""
        threshold = max(self.asin_floor, math.ceil(self.asin_ratio * asins_with_data))
        return hits >= self.hits_min and asin_count >= threshold

    @staticmethod
    def attention(mentions: int, total: int) -> float:
        return (mentions / total) if total else 0.0

    @staticmethod
    def net_sat(pos: int, neg: int, hits: int) -> float:
        return ((pos - neg) / hits) if hits else 0.0

    @staticmethod
    def satisfaction(pos: int, neg: int, hits: int) -> float:
        """``(net_sat + 1) / 2``（PRD §4.4）；``hits == 0`` 回退 0.5。

        ⚠️ 分母是 ``hits``（含 ``other`` 极性），**不是** ``pos + neg``——两者仅在
        ``other == 0`` 时相等，而 ``polarity ∈ pos|neg|neutral|mixed``（models.py），
        ``neutral``/``mixed`` 会落入 ``other``，故此处必须按 PRD 定义。
        """
        if hits <= 0:
            return 0.5
        return ((pos - neg) / hits + 1.0) / 2.0

    def opportunity(self, attention: float, satisfaction: float) -> float:
        return attention * (1.0 - satisfaction)

    @staticmethod
    def asin_opportunity(per_dim: list[tuple[float, float]]) -> float:
        """``Σ opportunity(d) × neg_share(d, a)``（PRD §7.4）。

        入参每项为 ``(opportunity(d), neg_share(d,a))``：**维度级**（全样本）机会分
        乘上**该 ASIN 局部**的负向占比。含义 = "该商品在最值得差异化的问题上糟糕到什么程度"。
        仅用于 ③ 矩阵选列，**不是**对外结论。``hits(d,a)==0`` 时 ``neg_share`` 由调用方
        置 0，该项自然不贡献。
        """
        return sum(opp * neg_share for opp, neg_share in per_dim)

    # ------------------------------------------------------------------ #
    # 主流程
    # ------------------------------------------------------------------ #
    def aggregate(
        self,
        records: list[ReviewRecord],
        dims: DimensionSet,
        *,
        reports: Optional[list[Any]] = None,
        titles: Optional[dict[str, str]] = None,
        generated_at: Optional[str] = None,
    ) -> Analysis:
        reports = reports or []
        titles = titles or {}

        scoring_ids = [d for d in dims.ids() if d not in EXCLUDED_FROM_OPPORTUNITY_IDS]

        usable = [r for r in records if r.is_usable]
        labeled_ok = [r for r in usable if r.labeling_ok]

        # ---- 逐维度统计（分母只算 usable & labeling.ok）----
        stats: dict[str, _DimStat] = {
            dim_id: _DimStat(dim_id) for dim_id in dims.ids()
        }
        other_counts: dict[str, int] = {}
        for record in labeled_ok:
            for label in record.labels:
                if label.dimension == OTHER_DIMENSION_ID:
                    if label.value:
                        other_counts[label.value] = other_counts.get(label.value, 0) + 1
                    continue
                stat = stats.get(label.dimension)
                if stat is None:
                    continue  # 未知维度（validate 应已拦截）
                stat.register(label, record)

        asins_with_data = sorted({r.asin for r in usable})
        n_asins_with_data = len(asins_with_data)

        # ---- 维度级结果 ----
        dimensions_out: list[dict[str, Any]] = []
        rankable_ids: set[str] = set()
        for dim_id, stat in stats.items():
            dim = dims.get(dim_id)
            attention = self.attention(stat.hits, len(labeled_ok))
            net_sat = self.net_sat(stat.pos, stat.neg, stat.hits)
            satisfaction = self.satisfaction(stat.pos, stat.neg, stat.hits)
            is_rankable = self.rankable(stat.hits, len(stat.asins), n_asins_with_data)
            if is_rankable:
                rankable_ids.add(dim_id)
            dimensions_out.append({
                "id": dim_id,
                "name": dim.name if dim else dim_id,
                "definition": dim.definition if dim else "",
                "attention": round(attention, 6),
                "net_sat": round(net_sat, 6),
                "satisfaction": round(satisfaction, 6),
                "pos_share": round(self.attention(stat.pos, stat.hits), 6),
                "neg_share": round(self.attention(stat.neg, stat.hits), 6),
                "hits": stat.hits,
                "asin_count": len(stat.asins),
                "rankable": is_rankable,
                "low_confidence": not is_rankable,   # 恒互补
            })
        dimensions_out.sort(key=lambda d: d["id"])

        # ---- by_asin（全量 ASIN；③ 按 opportunity 降序取 Top N 列）----
        by_asin: list[dict[str, Any]] = []
        for asin in asins_with_data:
            asin_records = [r for r in usable if r.asin == asin]
            asin_labeled = [r for r in asin_records if r.labeling_ok]
            per_dim_pairs: list[tuple[float, float]] = []
            per_dim_out: dict[str, dict[str, Any]] = {}
            for dim_id in scoring_ids:
                if dim_id not in rankable_ids:
                    continue
                # ★ 维度级机会分（全样本算）—— PRD §7.4：被乘的是它，而非 per-ASIN 量
                dim_stat = stats[dim_id]
                dim_opportunity = self.opportunity(
                    self.attention(dim_stat.hits, len(labeled_ok)),
                    self.satisfaction(dim_stat.pos, dim_stat.neg, dim_stat.hits),
                )
                hits = pos = neg = 0
                for record in asin_labeled:
                    for label in record.labels:
                        if label.dimension != dim_id:
                            continue
                        hits += 1
                        bucket = _bucket(label.polarity)
                        pos += 1 if bucket == "pos" else 0
                        neg += 1 if bucket == "neg" else 0
                attn = self.attention(hits, len(asin_labeled))
                # ★ 该 ASIN 在 d 上的负向占比（有界）；hits==0 → 0，不贡献
                per_dim_pairs.append((dim_opportunity, (neg / hits) if hits else 0.0))
                if hits:
                    per_dim_out[dim_id] = {
                        "attention": round(attn, 6),
                        "net_sat": round(self.net_sat(pos, neg, hits), 6),
                        "hits": hits,
                    }
            by_asin.append({
                "asin": asin,
                "title": titles.get(asin, ""),
                "rating_avg": self._rating_avg(asin_records),
                "opportunity": round(self.asin_opportunity(per_dim_pairs), 6),
                "dimensions": per_dim_out,
            })
        by_asin.sort(key=lambda a: (-a["opportunity"], a["asin"]))

        # ---- opportunities[]（仅 rankable 评分维；opportunity 降序）----
        opportunities: list[dict[str, Any]] = []
        for dim_id in scoring_ids:
            if dim_id not in rankable_ids:
                continue
            stat = stats[dim_id]
            dim = dims.get(dim_id)
            attention = self.attention(stat.hits, len(labeled_ok))
            satisfaction = self.satisfaction(stat.pos, stat.neg, stat.hits)
            opportunities.append({
                "dimension": dim_id,
                "opportunity": round(self.opportunity(attention, satisfaction), 6),
                "attention": round(attention, 6),
                "net_sat": round(self.net_sat(stat.pos, stat.neg, stat.hits), 6),
                "hits": stat.hits,
                "asin_count": len(stat.asins),
                "top_evidence": self._evidence(stat, prefer_neg=True),
                "supplier_action": self._supplier_action(dim, stat, prefer_neg=True),
            })
        opportunities.sort(key=lambda o: (-o["opportunity"], o["dimension"]))

        # ---- selection_priority[]（≤ 7）----
        selection_priority = [
            {
                "dimension": o["dimension"],
                "opportunity": o["opportunity"],
                "reason": self._priority_reason(dims.get(o["dimension"]), o),
            }
            for o in opportunities[:7]
        ]

        # ---- risk_flags[]（SAF；单列，不入机会分）----
        risk_flags = self._risk_flags(stats.get("SAF"), dims)

        # ---- filters（SCN 场景切片计数）----
        filters = self._filters(stats.get("SCN"), dims)

        # ---- top_praise / top_complaint ----
        top_praise = self._top_by_share(stats, dims, scoring_ids, which="pos")
        top_complaint = self._top_by_share(stats, dims, scoring_ids, which="neg")

        # ---- sample ----
        per_asin_sample = self._per_asin_sample(usable, reports, titles)
        labeled_coverage = (len(labeled_ok) / len(usable)) if usable else 0.0
        sample = {
            "asins": asins_with_data,
            "comments_total": len(records),
            "comments_usable": len(usable),
            "asins_with_data": n_asins_with_data,
            "labeled_coverage": round(labeled_coverage, 6),
            "date_range": self._date_range(usable),
            "per_asin": per_asin_sample,
        }

        # ---- data_quality ----
        data_quality = {
            "failed_asins": [s["asin"] for s in per_asin_sample if not s["ok"]],
            "underfilled_asins": [
                {"asin": s["asin"], "fetched": s["fetched"]}
                for s in per_asin_sample
                if s["fetched"] < config.TARGET_REVIEWS_PER_ASIN
            ],
            "low_confidence_dimensions": [
                {"id": d["id"], "hits": d["hits"], "asin_count": d["asin_count"],
                 "reason": self._low_conf_reason(d)}
                for d in dimensions_out if d["low_confidence"]
            ],
            "skipped_unusable": len([r for r in records if not r.is_usable]),
            "labeling_failures": len([r for r in usable if not r.labeling_ok]),
            "sampling_bias": dict(_SAMPLING_BIAS),
            "gate": None,
        }

        return Analysis(
            generated_at=generated_at or config.now_iso(),
            dimension_set_version=dims.version,
            sample=sample,
            dimensions=dimensions_out,
            by_asin=by_asin,
            top_praise=top_praise,
            top_complaint=top_complaint,
            opportunities=opportunities,
            selection_priority=selection_priority,
            risk_flags=risk_flags,
            filters=filters,
            other_topics=[
                {"topic_phrase": phrase, "count": count}
                for phrase, count in sorted(other_counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
            data_quality=data_quality,
        )

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _rating_avg(records: list[ReviewRecord]) -> float:
        ratings = [r.raw.get("rating") for r in records if r.raw.get("rating")]
        if not ratings:
            return 0.0
        return round(sum(ratings) / len(ratings), 4)

    @staticmethod
    def _date_range(records: list[ReviewRecord]) -> dict[str, str]:
        dates = sorted(r.raw.get("review_date", "") for r in records if r.raw.get("review_date"))
        if not dates:
            return {"from": "", "to": ""}
        return {"from": dates[0], "to": dates[-1]}

    def _evidence(self, stat: _DimStat, *, prefer_neg: bool) -> list[dict[str, str]]:
        source = stat.evidence_neg if prefer_neg else stat.evidence_pos
        if not source:
            source = stat.evidence_pos + stat.evidence_neg
        out: list[dict[str, str]] = []
        for quote, review_id, asin in source[: self.top_evidence_n]:
            out.append({"quote": quote, "review_id": review_id, "asin": asin})
        return out

    def _supplier_action(self, dim: Any, stat: _DimStat, *, prefer_neg: bool) -> str:
        name = dim.name if dim else stat.dim_id
        top_values = [v for v, _c in sorted(stat.value_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:2]]
        direction = "负" if prefer_neg else "正"
        detail = "、".join(top_values) if top_values else "-"
        return f"聚焦「{name}」{direction}反馈（{detail}），复核工艺与描述一致性"

    def _priority_reason(self, dim: Any, opp: dict[str, Any]) -> str:
        name = dim.name if dim else opp["dimension"]
        return (
            f"{name}：attention={opp['attention']}、net_sat={opp['net_sat']}、"
            f"跨 {opp['asin_count']} 个商品复现"
        )

    def _risk_flags(self, saf_stat: Optional[_DimStat], dims: DimensionSet) -> list[dict[str, Any]]:
        if saf_stat is None or saf_stat.hits == 0:
            return []
        dim = dims.get("SAF")
        flags: list[dict[str, Any]] = []
        for value, count in sorted(saf_stat.value_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            flags.append({
                "dimension": "SAF",
                "value": value,
                "polarity": "neutral",
                "hits": count,
                "top_evidence": self._evidence(saf_stat, prefer_neg=True),
            })
        return flags

    def _filters(self, scn_stat: Optional[_DimStat], dims: DimensionSet) -> dict[str, int]:
        dim = dims.get("SCN")
        values = dim.values if dim else []
        result = {value: 0 for value in values}
        if scn_stat is not None:
            for value, count in scn_stat.value_counts.items():
                result[value] = count
        return result

    def _top_by_share(
        self,
        stats: dict[str, _DimStat],
        dims: DimensionSet,
        scoring_ids: list[str],
        *,
        which: str,
    ) -> list[dict[str, Any]]:
        rows: list[tuple[float, str, _DimStat]] = []
        for dim_id in scoring_ids:
            stat = stats[dim_id]
            if stat.hits == 0:
                continue
            share = (stat.pos if which == "pos" else stat.neg) / stat.hits
            if share > 0:
                rows.append((share, dim_id, stat))
        rows.sort(key=lambda r: (-r[0], r[1]))
        out: list[dict[str, Any]] = []
        for share, dim_id, stat in rows[:3]:
            evidence = stat.evidence_pos if which == "pos" else stat.evidence_neg
            out.append({
                "dimension": dim_id,
                f"{which}_share": round(share, 6),
                "example_evidence": evidence[0][0] if evidence else "",
            })
        return out

    def _low_conf_reason(self, dim: dict[str, Any]) -> str:
        # 用实例阈值（可被构造器覆盖），不再读 config 常量
        if dim["hits"] < self.hits_min:
            return "hits_below_min"
        return "asin_coverage_below_min"

    def _per_asin_sample(
        self,
        usable: list[ReviewRecord],
        reports: list[Any],
        titles: dict[str, str],
    ) -> list[dict[str, Any]]:
        report_by_asin = {getattr(r, "asin", None): r for r in reports}
        asins = sorted({r.asin for r in usable} | {a for a in report_by_asin if a})
        out: list[dict[str, Any]] = []
        for asin in asins:
            asin_records = [r for r in usable if r.asin == asin]
            report = report_by_asin.get(asin)
            fetched = getattr(report, "fetched", len(asin_records)) if report else len(asin_records)
            out.append({
                "asin": asin,
                "title": titles.get(asin, ""),
                "fetched": fetched,
                "usable": len(asin_records),
                "rating_avg": self._rating_avg(asin_records),
                "ok": fetched >= config.MIN_REVIEWS_PER_ASIN,
            })
        out.sort(key=lambda s: s["asin"])
        return out


# --------------------------------------------------------------------------- #
# 便捷函数
# --------------------------------------------------------------------------- #

def aggregate(
    records: list[ReviewRecord],
    dims: DimensionSet,
    *,
    reports: Optional[list[Any]] = None,
    titles: Optional[dict[str, str]] = None,
    generated_at: Optional[str] = None,
) -> Analysis:
    """一次性聚合（无状态便捷入口）。"""
    return Aggregator().aggregate(
        records, dims, reports=reports, titles=titles, generated_at=generated_at
    )
