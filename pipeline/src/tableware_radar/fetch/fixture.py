"""离线/测试用固定数据 fetcher。

目的：让**下游（clean / stage_a / stage_c / aggregate）在探针结论未回、或没有
真实网络时也能开发与联调**（见 docs/ARCHITECTURE.md §2.1 该文件的职责说明）。

特点：

* **确定性**：以 ``sha1(asin)`` 为随机种子，同一 ASIN 每次产出完全一致的评论，
  便于测试断言与可复现构建。
* **覆盖脏数据边界**（给清洗层当靶子）：
  - 部分 ``helpful_votes is None``（无票评论，实测常态）；
  - 全部 ``variant is None``（商品页不提供）；
  - 至少一条 ``review_id == ""``（触发 ``clean`` 层的 sha1 兜底）；
  - 部分 ``body`` 含 ``"Brief content visible... Read more Read less"`` 噪声；
  - 部分 ``review_date`` 早于 24 个月窗口（触发窗口外丢弃）。

⚠️ 本模块产出的是**明确的测试夹具**，不是任何真实商品数据，不得当作结论依据。
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone

from .. import config
from ..models import FetchReport, RawReview

__all__ = ["FixtureFetcher"]

# 生成夹具评论用的小词库（英文，贴合"餐盘碗碟"品类语境）。
_POSITIVE_TITLES = [
    "Excellent quality plates",
    "Very happy with this set",
    "Perfect for everyday use",
    "Looks great on the table",
    "Great value for money",
]
_NEUTRAL_TITLES = [
    "Decent plates",
    "Does the job",
    "As described",
    "Reasonable quality",
]
_NEGATIVE_TITLES = [
    "Chips easily",
    "Not what I expected",
    "Arrived damaged",
    "Smaller than described",
]

_BODY_SNIPPETS = [
    "These plates feel sturdy and have a nice weight to them. They survived the dishwasher without any issues.",
    "The glaze is smooth and they stack neatly in the cupboard, saving space.",
    "Nice looking dinner plates, though one of them had a small chip on the rim out of the box.",
    "Good size for a main course. The packaging was minimal so a couple arrived with scratches.",
    "They are a bit heavier than my old set but overall I am pleased with the purchase.",
    "Colour is slightly different from the photos but still looks fine on the table.",
    "Bought for a dinner party and got several compliments. Easy to clean by hand too.",
    "Two plates were cracked in transit; the box had no protective padding.",
]

# 正文 UI 噪声（清洗层必须剔除，见 probe/REPORT.md §4-Q3/Q8）。
_NOISE = "Brief content visible, double tap to read full content. Read more Read less"


class FixtureFetcher:
    """确定性假数据抓取器。"""

    version: str = "0.1.0-fixture"

    def __init__(
        self,
        asins: tuple[str, ...] | list[str] | None = None,
        per_asin: int | None = None,
        *,
        with_noise: bool = True,
    ) -> None:
        self._asins: tuple[str, ...] = tuple(asins) if asins else config.ASINS
        self._per_asin: int = per_asin if per_asin is not None else config.TARGET_REVIEWS_PER_ASIN
        self._with_noise = with_noise

    # ---- Fetcher Protocol ----
    def fetch_reviews(self, asin: str, limit: int) -> tuple[list[RawReview], FetchReport]:
        reviews = self._generate(asin, limit)
        report = FetchReport(
            asin=asin,
            requested=limit,
            fetched=len(reviews),
            platform_cap=config.PLATFORM_CAP_PER_ASIN,
            ok=len(reviews) >= config.MIN_REVIEWS_PER_ASIN,
            attempts=1,
            fetcher_version=self.version,
            swapped_from=None,
            error="",
        )
        return reviews, report

    def fetch_all(self) -> tuple[list[RawReview], list[FetchReport]]:
        """便捷方法：抓取全部配置 ASIN（供离线联调）。"""
        all_reviews: list[RawReview] = []
        reports: list[FetchReport] = []
        for asin in self._asins:
            reviews, report = self.fetch_reviews(asin, config.FETCH_REQUEST_LIMIT)
            all_reviews.extend(reviews)
            reports.append(report)
        return all_reviews, reports

    # ---- 内部 ----
    def _generate(self, asin: str, limit: int) -> list[RawReview]:
        count = min(self._per_asin, limit) if limit and limit > 0 else self._per_asin
        seed = int(hashlib.sha1(asin.encode("utf-8")).hexdigest(), 16)
        rng = random.Random(seed)
        now = datetime.now(timezone.utc)
        url = f"{config.BASE_URL}/dp/{asin}"
        reviews: list[RawReview] = []

        for index in range(count):
            # 每条评论日期：多数落在 24 个月内，末位若干条故意落到窗口外。
            if index >= count - 2 and count > 3:
                days_ago = rng.randint(config.TIME_WINDOW_MONTHS * 30 + 30, config.TIME_WINDOW_MONTHS * 30 + 400)
            else:
                days_ago = rng.randint(3, config.TIME_WINDOW_MONTHS * 30 - 5)
            review_date = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")

            rating = rng.choices([5, 4, 3, 2, 1], weights=[45, 30, 15, 6, 4])[0]
            if rating >= 4:
                title = rng.choice(_POSITIVE_TITLES)
            elif rating == 3:
                title = rng.choice(_NEUTRAL_TITLES)
            else:
                title = rng.choice(_NEGATIVE_TITLES)

            body = rng.choice(_BODY_SNIPPETS)
            if self._with_noise and index % 3 == 0:
                body = f"{body} {_NOISE}"

            # review_id：首条故意置空以覆盖 sha1 兜底路径。
            review_id = "" if index == 0 else f"R{seed % 10**8:08d}{index:03d}"

            # helpful_votes：约 1/3 为 None（无票节点）。
            helpful_votes = None if index % 3 == 0 else rng.randint(0, 42)

            reviews.append(
                RawReview(
                    review_id=review_id,
                    asin=asin,
                    title=title,
                    body=body,
                    rating=rating,
                    review_date=review_date,
                    helpful_votes=helpful_votes,
                    country="GB",
                    verified_purchase=(index % 5 != 4),
                    variant=None,
                    url=url,
                )
            )
        return reviews
