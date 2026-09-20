"""清洗去重 —— ``RawReview`` → ``ReviewRecord``（docs/ARCHITECTURE.md §5 T03）。

职责（对应 T03 验收）：

1. **``review_id`` 兜底**：缺失时用 ``sha1(asin + review_date + title + body[:120])`` 生成稳定 ID
   （隐私：不落 reviewer 名称，见 §7）。
2. **去重**：按 ``review_id`` 去重，去重差额可见（``dedup_removed``）。
3. **去 HTML / 归一空白 / 正文噪声清洗**：噪声清洗复用 ``fetch.amazon_uk.clean_body_noise``（探针实测）。
4. **语言标记**：``content.lang``（``langdetect``，设固定 seed 保证可复现）。
5. **``is_usable`` 规则**：正文过短视为噪声，**不计入聚合分母**。
6. **★ 24 个月时间窗**：早于窗口的评论**丢弃且不写入任何中间产物**（不污染分母，U6）。

两条来自探针的「脏数据是常态」规则：

* ``helpful_votes`` 缺失 = **正常**（无票节点不存在，实测 7/13），**不得**当错误；
* ``variant`` 缺失 = **正常**（字段可空），保持 ``null``。实测商品页 review 节点带
  ``[data-hook="format-strip"]``，故本商品 13/13 有值（更正探针 REPORT 的「0/13」）。

本模块**纯函数 + 无 I/O**，落盘由 ``cli`` 负责。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

from . import config
from .fetch.amazon_uk import clean_body_noise
from .models import PLATFORM_MARKETPLACE, RawReview, ReviewRecord

__all__ = ["Cleaner", "CleanStats", "clean_reviews", "sha1_fallback_id"]

# langdetect 需要固定随机种子才能可复现。
try:  # pragma: no cover - 依赖存在性由环境保证
    from langdetect import DetectorFactory, detect

    DetectorFactory.seed = 0
except Exception:  # noqa: BLE001 - langdetect 缺失时降级为不做语言标记
    detect = None  # type: ignore[assignment]

_WS_RE = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# 统计
# --------------------------------------------------------------------------- #

@dataclass
class CleanStats:
    """清洗阶段统计（落 ``data_quality`` / 日志）。"""

    total_in: int = 0
    dropped_out_of_window: int = 0
    dedup_removed: int = 0
    skipped_unusable: int = 0
    id_backfilled: int = 0
    kept: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "total_in": self.total_in,
            "dropped_out_of_window": self.dropped_out_of_window,
            "dedup_removed": self.dedup_removed,
            "skipped_unusable": self.skipped_unusable,
            "id_backfilled": self.id_backfilled,
            "kept": self.kept,
        }


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def sha1_fallback_id(review: RawReview) -> str:
    """``review_id`` 缺失时的稳定兜底 ID。

    输入取自 ``asin + review_date + title + body[:120]``（不涉及 reviewer 身份）。
    """
    payload = "|".join([
        review.asin or "",
        review.review_date or "",
        review.title or "",
        (review.body or "")[:120],
    ])
    return "sha1-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _strip_html(text: str) -> str:
    if not text:
        return ""
    if "<" in text and ">" in text:
        try:
            return BeautifulSoup(text, "html.parser").get_text(" ", strip=False)
        except Exception:  # noqa: BLE001
            return text
    return text


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def _detect_lang(text: str) -> str:
    if detect is None or not text or len(text) < 8:
        return "en"
    try:
        return detect(text)
    except Exception:  # noqa: BLE001
        return "en"


def _within_window(date_str: str, now: datetime, months: int) -> bool:
    """评论是否落在最近 ``months`` 个月内（判据唯一定义在 ``config.within_window``）。

    日期缺失（``""``）无法判定，**保留**（宁可保留也不误删，见模块 docstring）。
    抓取层已按同一判据**不落盘**窗口外评论，这里是第二道兜底（U6）。
    """
    return config.within_window(date_str, now=now, months=months)


# --------------------------------------------------------------------------- #
# 清洗器
# --------------------------------------------------------------------------- #

class Cleaner:
    """把 ``RawReview`` 批量清洗为 ``ReviewRecord``。"""

    def __init__(
        self,
        *,
        fetcher_version: Optional[str] = None,
        time_window_months: Optional[int] = None,
        min_usable_chars: Optional[int] = None,
        marketplace: str = PLATFORM_MARKETPLACE,
    ) -> None:
        self.fetcher_version = fetcher_version or config.FETCHER_VERSION
        self.time_window_months = (
            time_window_months if time_window_months is not None else config.TIME_WINDOW_MONTHS
        )
        self.min_usable_chars = (
            min_usable_chars if min_usable_chars is not None else config.MIN_USABLE_CHARS
        )
        self.marketplace = marketplace
        self.stats = CleanStats()

    # ---- 主流程 ----
    def clean(
        self,
        reviews: list[RawReview],
        *,
        now: Optional[datetime] = None,
    ) -> list[ReviewRecord]:
        """清洗 + 去重，返回**时间窗内、去重后**的记录（含 unusable，供覆盖率统计）。

        ⚠️ 时间窗外的评论在**生成 ReviewRecord 之前**即被丢弃，**不写入任何中间产物**。
        """
        now = now or datetime.now(timezone.utc)
        self.stats = CleanStats()

        records: list[ReviewRecord] = []
        for review in reviews:
            self.stats.total_in += 1
            if not _within_window(review.review_date, now, self.time_window_months):
                self.stats.dropped_out_of_window += 1
                continue
            record = self._to_record(review, now)
            if record.review_id == "":
                # 理论不可达：_to_record 已兜底。保留防御。
                self.stats.id_backfilled += 1
                record.review_id = sha1_fallback_id(review)
            records.append(record)

        records = self.dedupe(records)
        self.stats.kept = len(records)
        self.stats.skipped_unusable = sum(1 for r in records if not r.is_usable)
        return records

    # ---- 去重 ----
    def dedupe(self, records: list[ReviewRecord]) -> list[ReviewRecord]:
        """按 ``review_id`` 去重，保留首次出现；去重差额记入 ``stats.dedup_removed``。"""
        seen: set[str] = set()
        unique: list[ReviewRecord] = []
        for record in records:
            if record.review_id in seen:
                self.stats.dedup_removed += 1
                continue
            seen.add(record.review_id)
            unique.append(record)
        return unique

    # ---- 可用性 ----
    def is_usable(self, record: ReviewRecord) -> bool:
        """可用性规则：正文（含标题）清洗后字符数 >= ``min_usable_chars``。

        ``helpful_votes`` / ``variant`` 缺失**不影响**可用性（探针结论：缺失是常态）。
        """
        text = str(record.content.get("text", "") or "")
        return len(text) >= self.min_usable_chars

    # ---- 内部 ----
    def _to_record(self, review: RawReview, now: datetime) -> ReviewRecord:
        review_id = (review.review_id or "").strip()
        if not review_id:
            review_id = sha1_fallback_id(review)
            self.stats.id_backfilled += 1

        title = _normalize(_strip_html(review.title))
        body = _normalize(clean_body_noise(_strip_html(review.body)))
        text = _normalize(f"{title}\n{body}") if title else body

        content = {
            "text": text,
            "lang": _detect_lang(text),
            "token_count": len(text.split()),
            "is_usable": len(text) >= self.min_usable_chars,
        }

        source = {
            "url": review.url,
            "fetched_at": config.now_iso(),
            "fetcher_version": self.fetcher_version,
            "verified_purchase": bool(review.verified_purchase),
            "variant": review.variant,          # 可空（常态）
        }

        raw = {
            "rating": int(review.rating),
            "title": review.title or "",
            "body": review.body or "",
            "review_date": review.review_date or "",
            "helpful_votes": review.helpful_votes,   # 可空（常态）
            "country": review.country or "",
        }

        labeling = {
            "ok": False,
            "error": "pending_labeling",
            "model": "",
            "prompt_version": config.PROMPT_VERSION,
            "dimension_set_version": config.DIMENSION_SET_VERSION,
            "labeled_at": "",
            "attempts": 0,
        }

        return ReviewRecord(
            review_id=review_id,
            asin=review.asin,
            source=source,
            raw=raw,
            content=content,
            labels=[],
            labeling=labeling,
            derived={},
        )


# --------------------------------------------------------------------------- #
# 便捷函数
# --------------------------------------------------------------------------- #

def clean_reviews(
    reviews: list[RawReview],
    *,
    fetcher_version: Optional[str] = None,
    now: Optional[datetime] = None,
) -> tuple[list[ReviewRecord], CleanStats]:
    """一次性清洗（无状态便捷入口），返回 ``(记录, 统计)``。"""
    cleaner = Cleaner(fetcher_version=fetcher_version)
    records = cleaner.clean(reviews, now=now)
    return records, cleaner.stats
