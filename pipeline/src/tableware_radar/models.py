"""纯数据类 —— 管道各阶段之间传递的稳定契约。

字段与 ``docs/ARCHITECTURE.md`` §3 严格对齐：

* ``RawReview`` / ``FetchReport``  —— 抓取层薄接口契约（§3.3）
* ``Label`` / ``ReviewRecord``     —— 打标记录 schema（§3.1）
* ``Dimension``                    —— 维度体系单元（§3.6 / *dimensions.yaml*）
* ``Analysis``                     —— ``analysis.json``（§3.2，页面唯一真源）

本模块**只定义数据与序列化**，不含任何 I/O 或业务规则（清洗、聚合各自独立）。
所有 ``to_dict`` 都产出可直接 ``json.dumps`` 的普通字典。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = [
    "PLATFORM_MARKETPLACE",
    "RawReview",
    "FetchReport",
    "Label",
    "ReviewRecord",
    "Dimension",
    "Analysis",
]

# 抓取面标记的默认市场（与 config.MARKETPLACE 语义一致，此处避免反向依赖）。
PLATFORM_MARKETPLACE = "amazon.co.uk"


# --------------------------------------------------------------------------- #
# 抓取层（§3.3）
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class RawReview:
    """抓取层产出的单条评论（未清洗）。

    约束（★ v1.3）：

    * ``review_id`` 缺失时置 ``""``，由 ``clean`` 层用 ``sha1`` 兜底。
    * ``helpful_votes`` **可空**：无票评论无对应节点（探针实测 7/13 有值）。
    * ``variant`` **可空**：商品页 review 节点的 ``[data-hook="format-strip"]`` 提供
      （T04 实测 13/13 = ``"Size Name: 10.5 Inch"``；**更正**探针 REPORT 原先「0/13」的说法）。
      字段契约仍是 ``Optional[str]``，缺失时保持 ``None``。
    * ``review_date`` 缺失允许 ``""``（``YYYY-MM-DD``）。
    """

    review_id: str
    asin: str
    title: str
    body: str
    rating: int                       # 1..5
    review_date: str                  # YYYY-MM-DD（缺失为 ""）
    helpful_votes: Optional[int] = None
    country: str = ""
    verified_purchase: bool = False
    variant: Optional[str] = None
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "asin": self.asin,
            "title": self.title,
            "body": self.body,
            "rating": self.rating,
            "review_date": self.review_date,
            "helpful_votes": self.helpful_votes,
            "country": self.country,
            "verified_purchase": self.verified_purchase,
            "variant": self.variant,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RawReview":
        return cls(
            review_id=str(data.get("review_id", "") or ""),
            asin=str(data.get("asin", "") or ""),
            title=str(data.get("title", "") or ""),
            body=str(data.get("body", "") or ""),
            rating=int(data.get("rating", 0) or 0),
            review_date=str(data.get("review_date", "") or ""),
            helpful_votes=_opt_int(data.get("helpful_votes")),
            country=str(data.get("country", "") or ""),
            verified_purchase=bool(data.get("verified_purchase", False)),
            variant=_opt_str(data.get("variant")),
            url=str(data.get("url", "") or ""),
        )


@dataclass
class FetchReport:
    """单 ASIN 抓取结果判读（§3.3）。

    ``platform_cap`` 记录单 ASIN 平台硬上限（实测 13），使「是否抓全」可判读。
    """

    asin: str
    requested: int
    fetched: int
    platform_cap: int = 13
    ok: bool = False
    attempts: int = 1
    fetcher_version: str = ""
    swapped_from: Optional[str] = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "asin": self.asin,
            "requested": self.requested,
            "fetched": self.fetched,
            "platform_cap": self.platform_cap,
            "ok": self.ok,
            "attempts": self.attempts,
            "fetcher_version": self.fetcher_version,
            "swapped_from": self.swapped_from,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FetchReport":
        return cls(
            asin=str(data.get("asin", "") or ""),
            requested=int(data.get("requested", 0) or 0),
            fetched=int(data.get("fetched", 0) or 0),
            platform_cap=int(data.get("platform_cap", 13) or 13),
            ok=bool(data.get("ok", False)),
            attempts=int(data.get("attempts", 1) or 1),
            fetcher_version=str(data.get("fetcher_version", "") or ""),
            swapped_from=_opt_str(data.get("swapped_from")),
            error=str(data.get("error", "") or ""),
        )


# --------------------------------------------------------------------------- #
# 打标层（§3.1）
# --------------------------------------------------------------------------- #

@dataclass
class Label:
    """单条维度标签（§3.1 ``labels[]`` 元素）。

    * ``dimension``  ∈ dims.yaml 定义的大写 ID（或 ``OTHER``）。
    * ``dimension_name`` ★ 中文显示名，与 ``dimension`` 一一对应（必带）。
    * ``evidence`` ★ 英文原文 ≤160 字符、**不翻译**；无 evidence 视为不合格输出。
    """

    dimension: str
    dimension_name: str
    value: str
    polarity: str = "neutral"     # pos|neg|neutral|mixed
    confidence: float = 0.0
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "dimension_name": self.dimension_name,
            "value": self.value,
            "polarity": self.polarity,
            "confidence": round(float(self.confidence), 4),
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Label":
        return cls(
            dimension=str(data.get("dimension", "") or ""),
            dimension_name=str(data.get("dimension_name", "") or ""),
            value=str(data.get("value", "") or ""),
            polarity=str(data.get("polarity", "neutral") or "neutral"),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            evidence=str(data.get("evidence", "") or ""),
        )


@dataclass
class ReviewRecord:
    """清洗 + 打标后的完整记录（§3.1 一行一条 JSONL）。

    结构对 ``source`` / ``raw`` / ``content`` / ``labels`` / ``labeling`` / ``derived``
    分区保存，便于序列化与页面消费。``labeling.ok`` 为**必填**（R5）。
    """

    review_id: str
    asin: str
    source: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    content: dict[str, Any] = field(default_factory=dict)
    labels: list[Label] = field(default_factory=list)
    labeling: dict[str, Any] = field(default_factory=dict)
    derived: dict[str, Any] = field(default_factory=dict)

    # ---- 便捷属性 ----
    @property
    def is_usable(self) -> bool:
        return bool(self.content.get("is_usable", False))

    @property
    def labeling_ok(self) -> bool:
        return bool(self.labeling.get("ok", False))

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "asin": self.asin,
            "source": dict(self.source),
            "raw": dict(self.raw),
            "content": dict(self.content),
            "labels": [lbl.to_dict() for lbl in self.labels],
            "labeling": dict(self.labeling),
            "derived": dict(self.derived),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewRecord":
        return cls(
            review_id=str(data.get("review_id", "") or ""),
            asin=str(data.get("asin", "") or ""),
            source=dict(data.get("source", {}) or {}),
            raw=dict(data.get("raw", {}) or {}),
            content=dict(data.get("content", {}) or {}),
            labels=[Label.from_dict(x) for x in (data.get("labels", []) or [])],
            labeling=dict(data.get("labeling", {}) or {}),
            derived=dict(data.get("derived", {}) or {}),
        )


# --------------------------------------------------------------------------- #
# 维度体系（§3.6）
# --------------------------------------------------------------------------- #

@dataclass
class Dimension:
    """维度体系中的一个维度（*dimensions.yaml* 的单元）。

    四要素（PRD §4.2 / R4）：``definition``（定义）、``judgement``（判定依据）、
    ``values``（枚举）、``positive_examples`` / ``negative_examples``（正负极性例句）；
    ★ 另需 ``excluded_from_opportunity``（是否参与机会分排序，``SCN``/``SAF`` 为 ``True``）。
    """

    id: str
    name: str                                  # 中文显示名
    definition: str = ""
    judgement: str = ""
    values: list[str] = field(default_factory=list)
    positive_examples: list[str] = field(default_factory=list)
    negative_examples: list[str] = field(default_factory=list)
    excluded_from_opportunity: bool = False
    version: str = "dims-v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "definition": self.definition,
            "judgement": self.judgement,
            "values": list(self.values),
            "positive_examples": list(self.positive_examples),
            "negative_examples": list(self.negative_examples),
            "excluded_from_opportunity": self.excluded_from_opportunity,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Dimension":
        return cls(
            id=str(data.get("id", "") or ""),
            name=str(data.get("name", "") or ""),
            definition=str(data.get("definition", "") or ""),
            judgement=str(data.get("judgement", "") or ""),
            values=[str(v) for v in (data.get("values", []) or [])],
            positive_examples=[str(v) for v in (data.get("positive_examples", []) or [])],
            negative_examples=[str(v) for v in (data.get("negative_examples", []) or [])],
            excluded_from_opportunity=bool(data.get("excluded_from_opportunity", False)),
            version=str(data.get("version", "dims-v1") or "dims-v1"),
        )


# --------------------------------------------------------------------------- #
# analysis.json（§3.2，页面唯一真源）
# --------------------------------------------------------------------------- #

@dataclass
class Analysis:
    """聚合打分结果 —— 与 ``analysis.json`` schema 一一对应。

    ⚠️ **不含任何候选款 / 我方款式字段**（PRD §9.1 边界）：矩阵只渲染真实 ASIN 列。
    """

    generated_at: str = ""
    dimension_set_version: str = "dims-v1"
    sample: dict[str, Any] = field(default_factory=dict)
    dimensions: list[dict[str, Any]] = field(default_factory=list)
    by_asin: list[dict[str, Any]] = field(default_factory=list)
    top_praise: list[dict[str, Any]] = field(default_factory=list)
    top_complaint: list[dict[str, Any]] = field(default_factory=list)
    opportunities: list[dict[str, Any]] = field(default_factory=list)
    selection_priority: list[dict[str, Any]] = field(default_factory=list)
    risk_flags: list[dict[str, Any]] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    other_topics: list[dict[str, Any]] = field(default_factory=list)
    data_quality: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "dimension_set_version": self.dimension_set_version,
            "sample": self.sample,
            "dimensions": self.dimensions,
            "by_asin": self.by_asin,
            "top_praise": self.top_praise,
            "top_complaint": self.top_complaint,
            "opportunities": self.opportunities,
            "selection_priority": self.selection_priority,
            "risk_flags": self.risk_flags,
            "filters": self.filters,
            "other_topics": self.other_topics,
            "data_quality": self.data_quality,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Analysis":
        return cls(
            generated_at=str(data.get("generated_at", "") or ""),
            dimension_set_version=str(data.get("dimension_set_version", "dims-v1") or "dims-v1"),
            sample=dict(data.get("sample", {}) or {}),
            dimensions=list(data.get("dimensions", []) or []),
            by_asin=list(data.get("by_asin", []) or []),
            top_praise=list(data.get("top_praise", []) or []),
            top_complaint=list(data.get("top_complaint", []) or []),
            opportunities=list(data.get("opportunities", []) or []),
            selection_priority=list(data.get("selection_priority", []) or []),
            risk_flags=list(data.get("risk_flags", []) or []),
            filters=dict(data.get("filters", {}) or {}),
            other_topics=list(data.get("other_topics", []) or []),
            data_quality=dict(data.get("data_quality", {}) or {}),
        )


# --------------------------------------------------------------------------- #
# 私有工具
# --------------------------------------------------------------------------- #

def _opt_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
