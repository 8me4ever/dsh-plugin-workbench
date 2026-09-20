"""T01 验收测试：数据模型 + 薄抓取接口 + 配置项。

覆盖（对应 ARCHITECTURE §5 T01 验收）：

* ``RawReview`` / ``FetchReport`` / ``Label`` / ``ReviewRecord`` / ``Dimension`` /
  ``Analysis`` 的字段与序列化往返；
* ``RawReview`` 含 ``review_date`` / ``helpful_votes: int|None`` / ``variant: str|None``；
* ``config`` 的 24 个月时间窗、``rankable`` 三阈值、矩阵列数、每 ASIN 目标条数，
  且 **ASIN 清单可配置（环境变量 / 文件 / 默认三级回退）**；
* ``FixtureFetcher`` 按 ``config.ASINS`` 产出「ASIN 数 × 每 ASIN ~13 条」假数据，确定性；
* ``get_fetcher()`` 工厂可切换 ``fixture | amazon_uk``（后者不触发网络）；
* ``amazon_uk`` 的纯解析函数可**离线**用合成 HTML 验证（不依赖 scrapling）。
"""

from __future__ import annotations

import math

import pytest

from tableware_radar import config
from tableware_radar.fetch import FixtureFetcher, get_fetcher
from tableware_radar.fetch import amazon_uk
from tableware_radar.models import (
    Analysis,
    Dimension,
    FetchReport,
    Label,
    RawReview,
    ReviewRecord,
)


# --------------------------------------------------------------------------- #
# RawReview
# --------------------------------------------------------------------------- #

def test_raw_review_optional_fields_default_none():
    review = RawReview(review_id="", asin="B0TEST", title="t", body="b", rating=4, review_date="2025-01-02")
    assert review.helpful_votes is None      # ★ v1.3 可空
    assert review.variant is None            # ★ v1.3 可空
    assert review.country == ""
    assert review.verified_purchase is False
    assert review.url == ""


def test_raw_review_roundtrip():
    review = RawReview(
        review_id="R12345678", asin="B0TEST", title="Nice", body="Body text",
        rating=5, review_date="2025-06-04", helpful_votes=7, country="GB",
        verified_purchase=True, variant="Colour: White", url="https://x/dp/B0TEST",
    )
    restored = RawReview.from_dict(review.to_dict())
    assert restored == review


def test_raw_review_from_dict_tolerates_missing():
    review = RawReview.from_dict({"asin": "B0X"})
    assert review.review_id == ""
    assert review.rating == 0
    assert review.helpful_votes is None
    assert review.variant is None


# --------------------------------------------------------------------------- #
# FetchReport
# --------------------------------------------------------------------------- #

def test_fetch_report_roundtrip_and_cap():
    report = FetchReport(
        asin="B0TEST", requested=100, fetched=13, platform_cap=13,
        ok=True, attempts=2, fetcher_version="0.1.0", swapped_from="B0OLD", error="",
    )
    restored = FetchReport.from_dict(report.to_dict())
    assert restored == report
    assert restored.platform_cap == 13        # ★ 平台硬上限可判读


# --------------------------------------------------------------------------- #
# Label / ReviewRecord
# --------------------------------------------------------------------------- #

def test_label_carries_dimension_name_and_evidence():
    label = Label(
        dimension="DUR", dimension_name="耐用性", value="durable_strong",
        polarity="pos", confidence=0.83, evidence="These plates feel sturdy",
    )
    data = label.to_dict()
    assert data["dimension_name"] == "耐用性"      # ★ 中英双语
    assert data["evidence"] == "These plates feel sturdy"
    assert Label.from_dict(data) == label


def test_review_record_roundtrip_and_flags():
    record = ReviewRecord(
        review_id="R1", asin="B0TEST",
        source={"url": "u", "verified_purchase": True, "variant": None},
        raw={"rating": 4},
        content={"text": "clean", "lang": "en", "token_count": 1, "is_usable": True},
        labels=[Label(dimension="CLE", dimension_name="易清洁", value="easy_to_clean", evidence="easy to clean")],
        labeling={"ok": True, "attempts": 1},
        derived={"sentiment_overall": "pos"},
    )
    assert record.is_usable is True
    assert record.labeling_ok is True
    restored = ReviewRecord.from_dict(record.to_dict())
    assert restored == record


def test_review_record_labeling_ok_false_still_counted():
    record = ReviewRecord(
        review_id="R2", asin="B0TEST",
        content={"is_usable": True},
        labels=[],
        labeling={"ok": False, "error": "timeout", "attempts": 3},
    )
    assert record.is_usable is True
    assert record.labeling_ok is False       # ★ 计入 labeled_coverage 分母


# --------------------------------------------------------------------------- #
# Dimension / Analysis
# --------------------------------------------------------------------------- #

def test_dimension_roundtrip_with_exclusion_flag():
    dim = Dimension(
        id="SAF", name="合规/安全", definition="d", judgement="j",
        values=["lead_free_claim", "food_safe_claim"],
        excluded_from_opportunity=True,
    )
    data = dim.to_dict()
    assert data["excluded_from_opportunity"] is True   # ★ SCN/SAF 排除机会分
    assert Dimension.from_dict(data) == dim


def test_analysis_to_dict_has_no_candidate_fields():
    analysis = Analysis(generated_at="2026-01-01T00:00:00Z", filters={"gifting": 0})
    data = analysis.to_dict()
    # §3.2 关键键齐备
    for key in (
        "generated_at", "dimension_set_version", "sample", "dimensions", "by_asin",
        "top_praise", "top_complaint", "opportunities", "selection_priority",
        "risk_flags", "filters", "other_topics", "data_quality",
    ):
        assert key in data
    # §9.1 边界：不含任何候选款字段
    assert not any("candidate" in k.lower() for k in data)
    assert Analysis.from_dict(data) == analysis


# --------------------------------------------------------------------------- #
# config：时间窗 / rankable 阈值 / ASIN 可配置
# --------------------------------------------------------------------------- #

def test_time_window_constant():
    assert config.TIME_WINDOW_MONTHS == 24      # ★ U6


def test_rankable_threshold_is_proportional_and_configurable():
    # 比例式：max(FLOOR, ceil(RATIO × asins_with_data))
    assert config.rankable_asin_threshold(0) == config.RANKABLE_ASIN_FLOOR
    for n in (8, 10, 30):
        expected = max(config.RANKABLE_ASIN_FLOOR, math.ceil(config.RANKABLE_ASIN_RATIO * n))
        assert config.rankable_asin_threshold(n) == expected
    # 扩容到 30 个 ASIN 时阈值随比例上升（护栏不被稀释）
    assert config.rankable_asin_threshold(30) > config.rankable_asin_threshold(8)


def test_config_matrix_and_target_are_present():
    assert config.MATRIX_TOP_ASINS_MIN <= config.MATRIX_TOP_ASINS <= config.MATRIX_TOP_ASINS_MAX
    assert config.TARGET_REVIEWS_PER_ASIN == config.PLATFORM_CAP_PER_ASIN == 13


def test_load_asins_from_env(monkeypatch):
    monkeypatch.setenv("TABLEWARE_ASINS", "b0aaa111, B0BBB222 ,, b0aaa111")
    asins = config.load_asins()
    assert asins == ("B0AAA111", "B0BBB222")    # 归一化 + 去重 + 保序


def test_load_asins_from_file(monkeypatch, tmp_path):
    asin_file = tmp_path / "asins.txt"
    asin_file.write_text("# comment\nB0FILE01\nB0FILE02  # inline\n\n", encoding="utf-8")
    monkeypatch.delenv("TABLEWARE_ASINS", raising=False)
    monkeypatch.setattr(config, "ASINS_FILE", asin_file)
    asins = config.load_asins()
    assert asins == ("B0FILE01", "B0FILE02")


def test_load_asins_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.delenv("TABLEWARE_ASINS", raising=False)
    monkeypatch.setattr(config, "ASINS_FILE", tmp_path / "does_not_exist.txt")
    assert config.load_asins() == config.DEFAULT_ASINS


# --------------------------------------------------------------------------- #
# FixtureFetcher
# --------------------------------------------------------------------------- #

def test_fixture_fetcher_produces_target_count():
    fetcher = FixtureFetcher(asins=("B0TEST01",), per_asin=13)
    reviews, report = fetcher.fetch_reviews("B0TEST01", config.FETCH_REQUEST_LIMIT)
    assert len(reviews) == 13
    assert report.fetched == 13
    assert report.ok is True
    assert report.platform_cap == config.PLATFORM_CAP_PER_ASIN


def test_fixture_fetcher_length_times_count(monkeypatch):
    # ★ 「ASIN 数 × 每 ASIN 条数」——ASIN 清单完全由配置驱动
    monkeypatch.setenv("TABLEWARE_ASINS", ",".join(f"B0FIX{i:04d}" for i in range(10)))
    asins = config.load_asins()
    assert len(asins) == 10
    fetcher = FixtureFetcher(asins=asins, per_asin=13)
    all_reviews, reports = fetcher.fetch_all()
    assert len(reports) == 10
    assert len(all_reviews) == 130
    assert all(r.ok for r in reports)


def test_fixture_fetcher_is_deterministic():
    a = FixtureFetcher(asins=("B0TEST01",), per_asin=13).fetch_reviews("B0TEST01", 100)
    b = FixtureFetcher(asins=("B0TEST01",), per_asin=13).fetch_reviews("B0TEST01", 100)
    assert [r.to_dict() for r in a[0]] == [r.to_dict() for r in b[0]]


def test_fixture_fetcher_exercises_dirty_paths():
    reviews, _ = FixtureFetcher(asins=("B0TEST01",), per_asin=13).fetch_reviews("B0TEST01", 100)
    assert any(r.review_id == "" for r in reviews)          # sha1 兜底靶子
    assert any(r.helpful_votes is None for r in reviews)    # 可空常态
    assert all(r.variant is None for r in reviews)          # 商品页无 variant
    assert any("Read more" in r.body for r in reviews)      # 噪声靶子（清洗层用）


# --------------------------------------------------------------------------- #
# get_fetcher 工厂
# --------------------------------------------------------------------------- #

def test_get_fetcher_switches_impl():
    assert isinstance(get_fetcher("fixture"), FixtureFetcher)
    amazon = get_fetcher("amazon_uk")
    assert amazon.version == config.FETCHER_VERSION
    # 惰性导入：仅实例化不会拉入 scrapling
    assert type(amazon).__name__ == "ScraplingAmazonUkFetcher"


def test_get_fetcher_unknown_raises():
    with pytest.raises(ValueError):
        get_fetcher("nope")


def test_get_fetcher_defaults_to_config(monkeypatch):
    monkeypatch.setattr(config, "FETCHER_NAME", "fixture")
    assert isinstance(get_fetcher(), FixtureFetcher)


# --------------------------------------------------------------------------- #
# amazon_uk 纯解析（离线，无需 scrapling）
# --------------------------------------------------------------------------- #

_SAMPLE_REVIEW_HTML = """
<html><body>
<div id="customer_review-RU77ORJODNV3R" data-hook="review">
  <i data-hook="review-star-rating"><span class="a-icon-alt">4.0 out of 5 stars</span></i>
  <a data-hook="review-title"><span>Excellent quality plates</span></a>
  <h5><span>Excellent quality plates</span></h5>
  <span data-hook="review-date">Reviewed in the United Kingdom on 3 November 2025</span>
  <span data-hook="avp-badge">Verified Purchase</span>
  <div data-hook="reviewText">
    These plates feel sturdy and survived the dishwasher.
    Brief content visible, double tap to read full content. Read more Read less
  </div>
  <span data-hook="helpful-vote-statement">12 people found this helpful</span>
  <div data-hook="format-strip">Colour: White</div>
</div>
</body></html>
"""


def test_clean_body_noise_strips_ui_text():
    cleaned = amazon_uk.clean_body_noise(
        "Great plates. Brief content visible, double tap to read full content. Read more Read less"
    )
    assert "Brief content visible" not in cleaned
    assert "Read more" not in cleaned
    assert cleaned.startswith("Great plates.")


def test_detect_block_and_product():
    blocked, marker = amazon_uk.detect_block("<html>Enter the characters you see below</html>")
    assert blocked is True
    assert marker == "Enter the characters you see below"
    assert amazon_uk.detect_product("<div id=\"productTitle\">Plates</div>") is True
    assert amazon_uk.detect_product("<html>nothing</html>") is False


def test_parse_helpful_votes_variants():
    assert amazon_uk.parse_helpful_votes("12 people found this helpful") == 12
    assert amazon_uk.parse_helpful_votes("1,234 people found this helpful") == 1234
    assert amazon_uk.parse_helpful_votes("One person found this helpful") == 1
    assert amazon_uk.parse_helpful_votes("") is None


def test_parse_date_and_country():
    date_iso, country = amazon_uk.parse_date_and_country(
        "Reviewed in the United Kingdom on 3 November 2025"
    )
    assert date_iso == "2025-11-03"
    assert country == "United Kingdom"


def test_parse_reviews_from_html_offline():
    reviews = amazon_uk.parse_reviews_from_html(_SAMPLE_REVIEW_HTML, "B0TEST01")
    assert len(reviews) == 1
    review = reviews[0]
    assert review.review_id == "RU77ORJODNV3R"
    assert review.rating == 4
    assert review.title == "Excellent quality plates"
    assert review.review_date == "2025-11-03"
    assert review.country == "United Kingdom"
    assert review.helpful_votes == 12
    assert review.verified_purchase is True
    assert review.variant == "Colour: White"
    # 正文噪声已被纯函数清洗
    assert "Brief content visible" not in review.body
    assert "Read more" not in review.body


def test_product_url_builder():
    assert amazon_uk.product_url("B0X") == f"{config.BASE_URL}/dp/B0X"
