"""Keyword-driven Amazon UK product discovery.

The discovery stage deliberately stops at a reviewable candidate manifest:
keyword -> search results -> relevance/safety filters -> stratified 8-10 item
sample.  It never starts the expensive review/LLM pipeline by itself.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import quote_plus, unquote, urljoin

from bs4 import BeautifulSoup

from . import config

_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
_NUMBER_RE = re.compile(r"([0-9][0-9,]*)")
_RATING_RE = re.compile(r"([0-5](?:\.[0-9])?)")
_PRICE_RE = re.compile(r"([0-9]+(?:[.,][0-9]{1,2})?)")
_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass
class ProductCandidate:
    asin: str
    title: str
    url: str
    price_gbp: float | None = None
    rating: float | None = None
    review_count: int = 0
    sponsored: bool = False
    relevance: float = 0.0
    selected: bool = False
    strata: list[str] = field(default_factory=list)
    selection_reasons: list[str] = field(default_factory=list)


@dataclass
class DiscoveryManifest:
    version: int
    keyword: str
    marketplace: str
    generated_at: str
    requested_count: int
    selected_count: int
    candidates: list[ProductCandidate]

    @property
    def selected_asins(self) -> tuple[str, ...]:
        return tuple(row.asin for row in self.candidates if row.selected)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["selected_asins"] = list(self.selected_asins)
        return data


def search_url(keyword: str) -> str:
    clean = " ".join(keyword.split())
    if not clean:
        raise ValueError("keyword cannot be empty")
    return f"{config.BASE_URL}/s?k={quote_plus(clean)}"


def parse_search_results(html: str, keyword: str) -> list[ProductCandidate]:
    """Parse organic and sponsored search cards without any network access."""
    soup = BeautifulSoup(html, "lxml")
    terms = set(_WORD_RE.findall(keyword.lower()))
    seen_asins: set[str] = set()
    seen_titles: set[str] = set()
    rows: list[ProductCandidate] = []
    for card in soup.select('[data-component-type="s-search-result"][data-asin]'):
        asin = str(card.get("data-asin", "")).strip().upper()
        if not _ASIN_RE.fullmatch(asin) or asin in seen_asins:
            continue
        title_node = card.select_one("h2 span") or card.select_one("h2")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        fingerprint = " ".join(_WORD_RE.findall(title.lower()))
        if not title or fingerprint in seen_titles:
            continue
        link = card.select_one("h2 a[href]") or card.select_one("a.a-link-normal[href]")
        href = str(link.get("href", "")) if link else f"/dp/{asin}"
        card_text = card.get_text(" ", strip=True)
        sponsored = "sponsored" in card_text.lower()
        rating = _first_float(_text(card.select_one(".a-icon-alt")), _RATING_RE)
        reviews = _first_int(_review_text(card))
        price = _first_float(_text(card.select_one(".a-price .a-offscreen")), _PRICE_RE)
        title_terms = set(_WORD_RE.findall(title.lower()))
        relevance = len(terms & title_terms) / max(1, len(terms))
        rows.append(ProductCandidate(
            asin=asin, title=title, url=urljoin(config.BASE_URL, href),
            price_gbp=price, rating=rating, review_count=reviews,
            sponsored=sponsored, relevance=round(relevance, 4),
        ))
        seen_asins.add(asin)
        seen_titles.add(fingerprint)
    return rows


def select_representative(
    candidates: Sequence[ProductCandidate], *, count: int = 10, min_reviews: int = 100,
) -> list[ProductCandidate]:
    """Select a deterministic, explainable sample across demand/rating/price."""
    if count < 1:
        raise ValueError("count must be positive")
    eligible_raw = [row for row in candidates if not row.sponsored and row.review_count >= min_reviews and row.relevance >= 0.5]
    eligible: list[ProductCandidate] = []
    for row in eligible_raw:
        if any(_same_variant_family(row.title, kept.title) for kept in eligible):
            continue
        eligible.append(row)
    for row in candidates:
        row.selected = False
        row.strata = []
        row.selection_reasons = []
    if not eligible:
        return []

    priced = sorted((row for row in eligible if row.price_gbp is not None), key=lambda row: row.price_gbp or 0)
    budget = set(row.asin for row in priced[: max(1, len(priced) // 3)])
    premium = set(row.asin for row in priced[-max(1, len(priced) // 3):])
    pools: list[tuple[str, list[ProductCandidate], str]] = [
        ("high_demand", sorted(eligible, key=lambda row: (-row.review_count, -(row.rating or 0))), "高评论量，代表已被市场验证的主流需求"),
        ("mid_rating", sorted(eligible, key=lambda row: (abs((row.rating or 0) - 4.1), -row.review_count)), "中等评分样本，用于识别购买阻碍"),
        ("budget", [row for row in priced if row.asin in budget], "较低价格带样本"),
        ("premium", list(reversed([row for row in priced if row.asin in premium])), "较高价格带样本"),
    ]
    selected: list[ProductCandidate] = []
    selected_ids: set[str] = set()
    while len(selected) < min(count, len(eligible)):
        progressed = False
        for stratum, pool, reason in pools:
            row = next((item for item in pool if item.asin not in selected_ids), None)
            if row is None:
                continue
            row.selected = True
            row.strata.append(stratum)
            row.selection_reasons.append(reason)
            selected.append(row)
            selected_ids.add(row.asin)
            progressed = True
            if len(selected) >= min(count, len(eligible)):
                break
        if not progressed:
            break
    for row in selected:
        if row.relevance >= 1:
            row.selection_reasons.append("标题完整命中品类关键词")
    return selected


class AmazonUkDiscovery:
    """Thin HTTP wrapper; tests inject ``get`` and stay fully offline."""

    def __init__(self, get: Callable[[str], Any] | None = None) -> None:
        self._get = get or self._scrapling_get

    def discover(self, keyword: str, *, count: int = 10, min_reviews: int = 100) -> DiscoveryManifest:
        url = search_url(keyword)
        response = self._get(url)
        html = _html_of(response)
        lowered = html.lower()
        status = getattr(response, "status", None)
        if status not in (None, 200):
            raise RuntimeError(f"Amazon UK search returned HTTP {status}; keyword discovery is blocked")
        if not html or "robot check" in lowered or "validatecaptcha" in lowered or "gokuprops" in lowered:
            raise RuntimeError("Amazon UK search WAF blocked keyword discovery")
        candidates = parse_search_results(html, keyword)
        selected = select_representative(candidates, count=count, min_reviews=min_reviews)
        if len(selected) < min(8, count):
            raise RuntimeError(f"only {len(selected)} eligible products found; need at least {min(8, count)}")
        return DiscoveryManifest(
            version=1, keyword=" ".join(keyword.split()), marketplace=config.MARKETPLACE,
            generated_at=config.now_iso(), requested_count=count,
            selected_count=len(selected), candidates=candidates,
        )

    @staticmethod
    def _scrapling_get(url: str) -> Any:
        try:
            from scrapling.fetchers import Fetcher
        except ImportError as exc:
            raise RuntimeError("scrapling is required: pip install -r pipeline/requirements.txt") from exc
        return Fetcher.get(url, impersonate="chrome", stealthy_headers=True, timeout=config.FETCH_PAGE_TIMEOUT_S)


class YahooAmazonUkDiscovery:
    """Discover ASINs through Yahoo, then read every metric from Amazon UK."""

    def __init__(
        self,
        search_get: Callable[[str], Any] | None = None,
        product_get: Callable[[str], Any] | None = None,
    ) -> None:
        self._search_get = search_get or self._curl_get
        self._product_get = product_get or AmazonUkDiscovery._scrapling_get

    def discover(self, keyword: str, *, count: int = 10, min_reviews: int = 100) -> DiscoveryManifest:
        clean = " ".join(keyword.split())
        queries = (
            f"site:amazon.co.uk {clean}",
            f"site:amazon.co.uk {clean} set",
            f"site:amazon.co.uk large {clean}",
            f"site:amazon.co.uk premium {clean}",
        )
        found: dict[str, ProductCandidate] = {}
        for query in queries:
            for start in (1, 11, 21):
                url = f"https://search.yahoo.com/search?p={quote_plus(query)}&b={start}"
                response = self._search_get(url)
                if getattr(response, "status_code", getattr(response, "status", 200)) != 200:
                    continue
                for row in parse_yahoo_results(_html_of(response), clean):
                    found.setdefault(row.asin, row)
        if len(found) < count:
            raise RuntimeError(f"search provider found only {len(found)} unique Amazon UK products")

        candidates: list[ProductCandidate] = []
        for discovered in list(found.values())[:30]:
            try:
                response = self._product_get(discovered.url)
                status = getattr(response, "status", getattr(response, "status_code", 200))
                if status != 200:
                    continue
                row = parse_product_page(_html_of(response), discovered.asin, clean)
                if row is not None:
                    candidates.append(row)
            except Exception:
                continue
            # Keep a real reserve pool after relevance/variant dedupe; raw
            # eligible counts are insufficient because multiple ASINs can be
            # near-identical variants of the same product family.
            representative = select_representative(candidates, count=count + 5, min_reviews=min_reviews)
            if len(representative) >= count + 5:
                break

        selected = select_representative(candidates, count=count, min_reviews=min_reviews)
        if len(selected) < min(8, count):
            raise RuntimeError(f"only {len(selected)} eligible products remained after Amazon detail checks")
        return DiscoveryManifest(
            version=1, keyword=clean, marketplace=config.MARKETPLACE,
            generated_at=config.now_iso(), requested_count=count,
            selected_count=len(selected), candidates=candidates,
        )

    @staticmethod
    def _curl_get(url: str) -> Any:
        try:
            from curl_cffi import requests
        except ImportError as exc:
            raise RuntimeError("curl_cffi is required by scrapling[fetchers]") from exc
        return requests.get(url, impersonate="chrome", timeout=config.FETCH_PAGE_TIMEOUT_S)


def parse_yahoo_results(html: str, keyword: str) -> list[ProductCandidate]:
    """Extract canonical Amazon UK ``/dp/<ASIN>`` targets from Yahoo redirects."""
    soup = BeautifulSoup(html, "lxml")
    terms = set(_WORD_RE.findall(keyword.lower()))
    rows: list[ProductCandidate] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = unquote(str(anchor.get("href", "")))
        redirect = re.search(r"/RU=(https?[^/]+)/RK=", href)
        target = unquote(redirect.group(1)) if redirect else href
        match = re.search(r"amazon\.co\.uk/(?:[^/?#]+/)?dp/([A-Z0-9]{10})", target, re.I)
        if not match:
            continue
        asin = match.group(1).upper()
        if asin in seen:
            continue
        title = anchor.get_text(" ", strip=True)
        title_terms = set(_WORD_RE.findall(title.lower()))
        rows.append(ProductCandidate(
            asin=asin, title=title, url=f"{config.BASE_URL}/dp/{asin}",
            relevance=round(len(terms & title_terms) / max(1, len(terms)), 4),
        ))
        seen.add(asin)
    return rows


def parse_product_page(html: str, asin: str, keyword: str) -> ProductCandidate | None:
    """Read selection metrics from the Amazon product page, never the search provider."""
    soup = BeautifulSoup(html, "lxml")
    title = _text(soup.select_one("#productTitle"))
    if not title:
        return None
    rating_text = _text(soup.select_one("#acrPopover")) or str((soup.select_one("#acrPopover") or {}).get("title", ""))
    rating = _first_float(rating_text, _RATING_RE)
    reviews = _first_int(_text(soup.select_one("#acrCustomerReviewText")))
    price = _amazon_price(soup)
    terms = set(_WORD_RE.findall(keyword.lower()))
    title_terms = set(_WORD_RE.findall(title.lower()))
    relevance = len(terms & title_terms) / max(1, len(terms))
    return ProductCandidate(
        asin=asin, title=title, url=f"{config.BASE_URL}/dp/{asin}",
        price_gbp=price, rating=rating, review_count=reviews,
        relevance=round(relevance, 4),
    )


def _amazon_price(soup: BeautifulSoup) -> float | None:
    whole = _text(soup.select_one(".a-price .a-price-whole")).replace(",", "").rstrip(".")
    fraction = _text(soup.select_one(".a-price .a-price-fraction"))
    if whole.isdigit():
        return float(f"{whole}.{fraction if fraction.isdigit() else '00'}")
    return _first_float(_text(soup.select_one(".a-price .a-offscreen")), _PRICE_RE)


def write_manifest(manifest: DiscoveryManifest, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _html_of(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, (bytes, bytearray)):
        return bytes(response).decode("utf-8", "replace")
    for attr in ("html_content", "body", "text"):
        value = getattr(response, attr, None)
        if value is not None:
            return bytes(value).decode("utf-8", "replace") if isinstance(value, (bytes, bytearray)) else str(value)
    return ""


def _text(node: Any) -> str:
    return node.get_text(" ", strip=True) if node is not None else ""


def _review_text(card: Any) -> str:
    for selector in ('a[href*="#customerReviews"] span', '[aria-label*="ratings"]', '.a-size-base.s-underline-text'):
        text = _text(card.select_one(selector))
        if text:
            return text
    return ""


def _first_int(text: str) -> int:
    match = _NUMBER_RE.search(text or "")
    return int(match.group(1).replace(",", "")) if match else 0


def _first_float(text: str, pattern: re.Pattern[str]) -> float | None:
    match = pattern.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _same_variant_family(left: str, right: str) -> bool:
    """Conservative variant dedupe: same brand plus highly overlapping title terms."""
    left_terms = [term for term in _WORD_RE.findall(left.lower()) if not term.isdigit()]
    right_terms = [term for term in _WORD_RE.findall(right.lower()) if not term.isdigit()]
    if not left_terms or not right_terms or left_terms[0] != right_terms[0]:
        return False
    a, b = set(left_terms), set(right_terms)
    return len(a & b) / max(1, len(a | b)) >= 0.68
