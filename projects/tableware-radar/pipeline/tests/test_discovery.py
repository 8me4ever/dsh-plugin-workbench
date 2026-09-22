"""Keyword discovery is fully testable without network access."""

from __future__ import annotations

import json
from pathlib import Path

from tableware_radar.cli import main
from tableware_radar.discovery import (
    AmazonUkDiscovery,
    DiscoveryManifest,
    ProductCandidate,
    parse_product_page,
    parse_search_results,
    parse_yahoo_results,
    search_url,
    select_representative,
)
import pytest


def _card(index: int, *, title: str | None = None, sponsored: bool = False) -> str:
    asin = f"B{index:09d}"
    name = title or f"Brand{index} Ceramic Pasta Bowls Set {index}"
    return f"""
    <div data-component-type="s-search-result" data-asin="{asin}">
      {'<span>Sponsored</span>' if sponsored else ''}
      <h2><a href="/dp/{asin}"><span>{name}</span></a></h2>
      <span class="a-icon-alt">{4.0 + (index % 6) / 10:.1f} out of 5 stars</span>
      <a href="#customerReviews"><span>{100 + index * 37:,}</span></a>
      <span class="a-price"><span class="a-offscreen">£{12 + index * 3}.99</span></span>
    </div>"""


def test_parse_search_results_extracts_comparable_fields():
    rows = parse_search_results(f"<html>{_card(1)}</html>", "ceramic pasta bowls")
    assert len(rows) == 1
    assert rows[0].asin == "B000000001"
    assert rows[0].title == "Brand1 Ceramic Pasta Bowls Set 1"
    assert rows[0].rating == 4.1
    assert rows[0].review_count == 137
    assert rows[0].price_gbp == 15.99
    assert rows[0].relevance == 1.0


def test_representative_selection_filters_ads_and_explains_strata():
    html = "<html>" + "".join(_card(i, sponsored=(i == 2)) for i in range(1, 13)) + _card(99, title="USB charging cable") + "</html>"
    rows = parse_search_results(html, "ceramic pasta bowls")
    selected = select_representative(rows, count=8, min_reviews=100)
    assert len(selected) == 8
    assert all(not row.sponsored and row.relevance >= 0.5 for row in selected)
    assert all(row.selection_reasons for row in selected)
    assert {stratum for row in selected for stratum in row.strata} >= {"high_demand", "mid_rating", "budget", "premium"}


def test_representative_selection_dedupes_same_brand_variants():
    rows = parse_search_results("<html>" + "".join(_card(i) for i in range(1, 10)) + "</html>", "ceramic pasta bowls")
    rows.extend([
        ProductCandidate(asin="B111111111", title="AHX Pasta Bowls Set of 6 Shallow Ceramic Bowls", url="x", review_count=1500, rating=4.7, relevance=1),
        ProductCandidate(asin="B222222222", title="AHX Pasta Bowls Set of 6 Shallow Ceramic Pasta Bowls Colourful", url="y", review_count=1400, rating=4.7, relevance=1),
    ])
    selected = select_representative(rows, count=10, min_reviews=100)
    assert len([row for row in selected if row.title.startswith("AHX ")]) == 1


def test_search_url_preserves_keyword_meaning():
    assert search_url(" ceramic  pasta bowls ").endswith("/s?k=ceramic+pasta+bowls")


def test_live_discovery_reports_search_wall_instead_of_empty_success():
    class Response:
        status = 202
        html_content = "<script>window.gokuProps = {}</script>"

    with pytest.raises(RuntimeError, match="HTTP 202"):
        AmazonUkDiscovery(get=lambda _url: Response()).discover("ceramic pasta bowls")


def test_yahoo_redirects_only_yield_amazon_product_pages():
    html = """
    <a href="https://r.search.yahoo.com/x/RU=https%3A%2F%2Fwww.amazon.co.uk%2FNice-Bowls%2Fdp%2FB09QWDJ9ZS/RK=2/x">Ceramic Pasta Bowls Set</a>
    <a href="https://example.com/dp/B000000000">Ignore me</a>
    """
    rows = parse_yahoo_results(html, "ceramic pasta bowls")
    assert [row.asin for row in rows] == ["B09QWDJ9ZS"]
    assert rows[0].url == "https://www.amazon.co.uk/dp/B09QWDJ9ZS"


def test_product_metrics_are_read_from_amazon_detail_html():
    html = """
    <h1 id="productTitle">Ceramic Pasta Bowls Set of 4</h1>
    <span id="acrPopover" title="4.4 out of 5 stars"></span>
    <span id="acrCustomerReviewText">1,554 ratings</span>
    <span class="a-price"><span class="a-price-whole">40</span><span class="a-price-fraction">93</span></span>
    """
    row = parse_product_page(html, "B09QWDJ9ZS", "ceramic pasta bowls")
    assert row is not None
    assert (row.rating, row.review_count, row.price_gbp, row.relevance) == (4.4, 1554, 40.93, 1.0)


def test_discover_cli_writes_confirmation_manifest(tmp_path: Path):
    rows = [ProductCandidate(
        asin=f"B{i:09d}", title=f"Ceramic Pasta Bowls {i}", url=f"https://www.amazon.co.uk/dp/B{i:09d}",
        review_count=100 + i, selected=True, selection_reasons=["test"],
    ) for i in range(1, 9)]
    manifest = DiscoveryManifest(
        version=1, keyword="ceramic pasta bowls", marketplace="amazon.co.uk",
        generated_at="2026-09-21T00:00:00Z", requested_count=8, selected_count=8, candidates=rows,
    )

    class FakeDiscovery:
        def discover(self, keyword: str, *, count: int, min_reviews: int):
            assert (keyword, count, min_reviews) == ("ceramic pasta bowls", 8, 100)
            return manifest

    output = tmp_path / "candidates.json"
    code = main([
        "discover", "--keyword", "ceramic pasta bowls", "--count", "8", "--output", str(output),
    ], discovery=FakeDiscovery())
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["selected_asins"] == [row.asin for row in rows]
    assert payload["keyword"] == "ceramic pasta bowls"
