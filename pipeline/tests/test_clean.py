"""T03 验收测试：清洗去重（纯离线，不依赖网络/LLM）。

覆盖：review_id sha1 兜底、去重差额、24 个月窗口外丢弃（不落产物）、
正文噪声/HTML 清洗、is_usable 规则、helpful_votes/variant 缺失不影响可用性。
"""

from __future__ import annotations

from datetime import datetime, timezone

from tableware_radar.clean import Cleaner, clean_reviews, sha1_fallback_id
from tableware_radar.models import RawReview

_NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _review(**overrides) -> RawReview:
    base = dict(
        review_id="R00000001",
        asin="B0TEST01",
        title="Great plates",
        body="These plates feel sturdy and survived the dishwasher without any issues.",
        rating=5,
        review_date="2026-08-01",
        helpful_votes=3,
        country="GB",
        verified_purchase=True,
        variant=None,
        url="https://www.amazon.co.uk/dp/B0TEST01",
    )
    base.update(overrides)
    return RawReview(**base)


# --------------------------------------------------------------------------- #
# review_id 兜底
# --------------------------------------------------------------------------- #

def test_sha1_fallback_when_id_missing():
    reviews = [_review(review_id="")]
    records, stats = clean_reviews(reviews, now=_NOW)
    assert len(records) == 1
    assert records[0].review_id.startswith("sha1-")
    assert stats.id_backfilled == 1


def test_sha1_fallback_is_stable():
    a = sha1_fallback_id(_review(review_id=""))
    b = sha1_fallback_id(_review(review_id=""))
    assert a == b


def test_sha1_fallback_differs_for_different_content():
    a = sha1_fallback_id(_review(review_id="", body="aaa"))
    b = sha1_fallback_id(_review(review_id="", body="bbb"))
    assert a != b


# --------------------------------------------------------------------------- #
# 去重
# --------------------------------------------------------------------------- #

def test_dedupe_by_review_id_reports_diff():
    reviews = [
        _review(review_id="R1", body="first body long enough to be usable yes"),
        _review(review_id="R1", body="duplicate content different but same id okay"),
        _review(review_id="R2", body="second unique body long enough to be usable"),
    ]
    records, stats = clean_reviews(reviews, now=_NOW)
    assert len(records) == 2
    assert stats.dedup_removed == 1


# --------------------------------------------------------------------------- #
# 24 个月时间窗
# --------------------------------------------------------------------------- #

def test_old_reviews_dropped_and_not_returned():
    reviews = [
        _review(review_id="R_NEW", review_date="2026-06-01"),
        _review(review_id="R_OLD", review_date="2022-01-01"),   # 远超 24 个月
    ]
    records, stats = clean_reviews(reviews, now=_NOW)
    assert stats.dropped_out_of_window == 1
    assert [r.review_id for r in records] == ["R_NEW"]
    assert all(r.review_id != "R_OLD" for r in records)


def test_missing_date_is_kept():
    records, stats = clean_reviews([_review(review_date="")], now=_NOW)
    assert len(records) == 1
    assert stats.dropped_out_of_window == 0


# --------------------------------------------------------------------------- #
# 正文清洗
# --------------------------------------------------------------------------- #

def test_noise_and_html_stripped():
    body = "<b>Nice</b> plates. Brief content visible, double tap to read full content. Read more Read less"
    records, _ = clean_reviews([_review(body=body)], now=_NOW)
    text = records[0].content["text"]
    assert "Read more" not in text
    assert "Brief content visible" not in text
    assert "<b>" not in text
    assert "Nice" in text


def test_token_count_and_lang():
    records, _ = clean_reviews([_review()], now=_NOW)
    content = records[0].content
    assert content["token_count"] == len(content["text"].split())
    assert content["lang"] == "en"


# --------------------------------------------------------------------------- #
# is_usable
# --------------------------------------------------------------------------- #

def test_short_text_not_usable():
    reviews = [_review(review_id="R_SHORT", title="", body="ok")]   # 过短
    records, stats = clean_reviews(reviews, now=_NOW)
    assert records[0].is_usable is False
    assert stats.skipped_unusable == 1


def test_long_text_usable():
    records, stats = clean_reviews([_review()], now=_NOW)
    assert records[0].is_usable is True
    assert stats.skipped_unusable == 0


def test_missing_helpful_votes_and_variant_do_not_break_usability():
    # 探针结论：两者缺失是常态，不得影响可用性。
    review = _review(helpful_votes=None, variant=None)
    records, _ = clean_reviews([review], now=_NOW)
    record = records[0]
    assert record.is_usable is True
    assert record.source["variant"] is None
    assert record.raw["helpful_votes"] is None


# --------------------------------------------------------------------------- #
# 记录结构
# --------------------------------------------------------------------------- #

def test_record_shape_and_pending_labeling():
    records, _ = clean_reviews([_review()], now=_NOW)
    record = records[0]
    data = record.to_dict()
    for key in ("review_id", "asin", "source", "raw", "content", "labels", "labeling", "derived"):
        assert key in data
    assert record.labeling["ok"] is False            # 未打标前
    assert record.labeling["error"] == "pending_labeling"
    assert record.source["fetcher_version"]          # 已注入版本
    assert record.labels == []


def test_cleaner_is_reusable_and_resets_stats():
    cleaner = Cleaner()
    cleaner.clean([_review(review_id="R1")], now=_NOW)
    first = cleaner.stats.dedup_removed
    cleaner.clean([_review(review_id="R1")], now=_NOW)
    assert cleaner.stats.dedup_removed == first == 0
