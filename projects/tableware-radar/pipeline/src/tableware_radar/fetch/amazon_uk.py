"""Amazon UK 抓取实现 —— 纯解析函数 + 薄抓取器 + 编排层。

本文件分三层，**刻意解耦**（team-lead 明确认可）：

1. **纯解析层（上半部）**：全部是接收 HTML 字符串 / BeautifulSoup 元素的
   **纯函数**，**零网络、零 scrapling 依赖**（只用 ``beautifulsoup4`` + ``python-dateutil``）。
   逻辑复用自探针 ``probe/probe_amazon_uk.py`` 的 L1 商品页 DOM 适配与正文噪声清洗
   （见 ``probe/REPORT.md`` §3/§4）。因为是纯函数，可以用存档 HTML 离线单测。
2. **薄抓取层（中部）**：``ScraplingAmazonUkFetcher`` 实现 ``Fetcher`` Protocol，
   默认且唯一的抓取口径 = **纯 HTTP ``Fetcher`` + ``impersonate='chrome'`` +
   ``stealthy_headers=True``**。``scrapling`` 在方法体内**惰性 import**，故导入本模块、
   运行离线解析单测均**不需要安装 scrapling**。
3. **编排层（下半部，T04）**：``AmazonUkRun`` 在薄抓取层之上补齐
   **重试 / 指数退避 / 换 ASIN 池 / 24 个月窗口截断 / ``fetch_report.json``**，
   产出 ``data/raw/raw_<asin>.json`` + ``data/raw/fetch_report.json``。

⚠️ 抓取口径（探针结论，勿违背）：

* **无浏览器 / 无代理 / 无登录 / 无翻页** —— 翻页在第 1 页即撞**登录墙（Amazon 政策墙，
  非反爬墙）**；浏览器路径对它无效。
* **禁用 ``solve_cloudflare``** —— Amazon 不使用 Cloudflare，与本项目无关。
* 单 ASIN 首屏硬上限 ≈ ``config.PLATFORM_CAP_PER_ASIN``（13）。
* 命中验证码 / 登录墙 **立即放弃该 ASIN**（记 ``FetchReport.error``，不硬刚），改从备选池换。
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from bs4 import BeautifulSoup

from .. import config
from ..models import FetchReport, RawReview

__all__ = [
    "BLOCK_MARKERS",
    "PRODUCT_MARKERS",
    "REVIEW_ITEM_SELECTORS",
    "product_url",
    "reviews_url",
    "html_of",
    "make_soup",
    "detect_block",
    "detect_product",
    "clean_body_noise",
    "parse_rating",
    "parse_date_and_country",
    "parse_helpful_votes",
    "parse_review_element",
    "parse_reviews",
    "parse_reviews_from_html",
    "extract_global_rating_count",
    "ScraplingAmazonUkFetcher",
    "AsinOutcome",
    "FetchRun",
    "AmazonUkRun",
    "is_hard_stop",
    "write_raw_reviews",
]


# --------------------------------------------------------------------------- #
# 常量（复用探针）
# --------------------------------------------------------------------------- #

# Amazon 反爬/异常拦截页特征串。
BLOCK_MARKERS = (
    "Enter the characters you see below",
    "Type the characters you see in this image",
    "Sorry, we just need to make sure you're not a robot",
    "api-services-support@amazon.com",
    "validateCaptcha",
    "To discuss automated access to Amazon data please contact",
    "Bots are not allowed",
    "Robot Check",
)

# 正常商品页特征。
PRODUCT_MARKERS = (
    'id="productTitle"',
    "id='productTitle'",
    'id="dp"',
    'data-hook="review"',
)

# 评论元素选择器（新旧 DOM 全部尝试；bs4 的 .select 支持 CSS）。
REVIEW_ITEM_SELECTORS = (
    '[data-hook="review"]',
    'li[data-hook="review"]',
    'div[data-hook="review"]',
    "#cm_cr-review_list [data-hook=\"review\"]",
)

# 正文噪声标记（清洗层与解析层共用；探针实测商品页挂件含此串）。
_BODY_NOISE_PATTERNS = (
    "Brief content visible, double tap to read full content.",
    "Brief content visible, double tap to read full content",
    "Brief content visible",
    "Read more",
    "Read less",
    "See more",
)

_RATING_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*out of\s*5")
_DATE_RE = re.compile(r"Reviewed in (?:the )?(.+?) on (.+)$")
_VOTES_RE = re.compile(r"([0-9,]+)")
_REVIEW_ID_RE = re.compile(r"(R[A-Z0-9]{8,})")
_REVIEW_ID_ALT_RE = re.compile(r"(?:review|customer_review)-([A-Za-z0-9]+)")
_VARIANT_RE = re.compile(r"^(Colour|Color|Size|Style|Flavour|Pattern)\s*:")


# --------------------------------------------------------------------------- #
# URL 构造
# --------------------------------------------------------------------------- #

def product_url(asin: str) -> str:
    """商品页 URL（唯一需要的入口；评论页需登录，不用）。"""
    return f"{config.BASE_URL}/dp/{asin}"


def reviews_url(asin: str, page: int = 1) -> str:
    """独立评论页 URL（**需登录**，保留以便诊断，不在默认流程使用）。"""
    url = f"{config.BASE_URL}/product-reviews/{asin}/"
    if page > 1:
        url += f"?pageNumber={page}&reviewerType=all_reviews"
    return url


# --------------------------------------------------------------------------- #
# 纯解析层（零网络 / 零 scrapling）
# --------------------------------------------------------------------------- #

def html_of(page: Any) -> str:
    """尽力从 scrapling Response/Selector 或原始字符串中取出 HTML 文本。"""
    if isinstance(page, str):
        return page
    if isinstance(page, (bytes, bytearray)):
        return bytes(page).decode("utf-8", "replace")
    for attr in ("html_content", "body"):
        try:
            value = getattr(page, attr)
        except Exception:  # noqa: BLE001 - 探针式兜底，任何属性访问失败都跳过
            continue
        if value is None:
            continue
        if isinstance(value, (bytes, bytearray)):
            return bytes(value).decode("utf-8", "replace")
        return str(value)
    return ""


def make_soup(html: str) -> BeautifulSoup:
    """构建 BeautifulSoup 文档。优先 lxml，缺失时回退内置解析器。"""
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001 - lxml 未安装时回退
        return BeautifulSoup(html, "html.parser")


def detect_block(html: str) -> tuple[bool, Optional[str]]:
    """检测是否命中反爬/异常拦截页。返回 ``(是否被拦, 命中的特征串)``。"""
    low = html.lower()
    for marker in BLOCK_MARKERS:
        if marker.lower() in low:
            return True, marker
    return False, None


def detect_product(html: str) -> bool:
    """粗判 HTML 是否为有效的商品页。"""
    return any(marker in html for marker in PRODUCT_MARKERS)


def clean_body_noise(text: str) -> str:
    """剔除评论正文里的 Amazon UI 噪声（探针实测，见 REPORT §4-Q8）。

    移除 ``"Brief content visible…"`` / ``"Read more"`` / ``"Read less"`` 等挂件文案，
    并归一空白。**这是纯函数，供解析层与 clean 层共用。**
    """
    if not text:
        return ""
    cleaned = text
    for pattern in _BODY_NOISE_PATTERNS:
        cleaned = cleaned.replace(pattern, " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def parse_rating(element: Any) -> int:
    """解析星级（1..5）。无法解析返回 ``0``（未知，交由清洗层判定可用性）。"""
    selectors = (
        '[data-hook="review-star-rating"] .a-icon-alt',
        '[data-hook="review-star-rating-view-point"] .a-icon-alt',
        '[data-hook="cmps-review-star-rating"]',
        ".review-rating .a-icon-alt",
        "i.a-icon-star .a-icon-alt",
        "i.a-icon-star span.a-icon-alt",
    )
    for selector in selectors:
        node = _select_one(element, selector)
        text = _text_of(node)
        if not text:
            continue
        match = _RATING_RE.search(text)
        if match:
            try:
                value = int(round(float(match.group(1))))
            except ValueError:
                continue
            return max(1, min(5, value))
    return 0


def parse_date_and_country(text: str) -> tuple[str, str]:
    """解析 ``"Reviewed in the United Kingdom on 3 November 2025"``。

    返回 ``(YYYY-MM-DD, country)``；解析失败时日期为 ``""``、国家尽力而为。
    """
    if not text:
        return "", ""
    country = ""
    date_iso = ""
    match = _DATE_RE.search(text.strip())
    if match:
        country = match.group(1).strip()
        raw_date = match.group(2).strip()
    else:
        raw_date = text.strip()
    date_iso = _to_iso_date(raw_date)
    return date_iso, country


def parse_helpful_votes(text: str) -> Optional[int]:
    """解析有用票数。无票节点返回 ``None``（缺失是常态）。"""
    if not text:
        return None
    lowered = text.lower()
    if "one person" in lowered:
        return 1
    match = _VOTES_RE.search(text)
    if match:
        try:
            return int(match.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def parse_review_element(element: Any, asin: str, url: str) -> RawReview:
    """把单个评论 DOM 元素解析成 ``RawReview``（纯函数）。"""
    review_id = _extract_review_id(element)
    rating = parse_rating(element)

    title = _extract_title(element)

    body_raw = _extract_body(element)
    body = clean_body_noise(body_raw)

    date_text = _text_of(_select_one(element, '[data-hook="review-date"]'))
    review_date, country = parse_date_and_country(date_text)

    helpful = parse_helpful_votes(
        _text_of(_select_one(element, '[data-hook="helpful-vote-statement"]'))
    )

    verified = _select_one(element, '[data-hook="avp-badge"]') is not None

    variant = _extract_variant(element)

    return RawReview(
        review_id=review_id,
        asin=asin,
        title=title,
        body=body,
        rating=rating,
        review_date=review_date,
        helpful_votes=helpful,
        country=country,
        verified_purchase=bool(verified),
        variant=variant,
        url=url,
    )


def parse_reviews(soup: BeautifulSoup, asin: str, url: str) -> list[RawReview]:
    """从已解析的 BeautifulSoup 文档中解析全部评论。"""
    items: list[Any] = []
    for selector in REVIEW_ITEM_SELECTORS:
        try:
            found = soup.select(selector)
        except Exception:  # noqa: BLE001 - 选择器异常不应中断整体解析
            continue
        if found:
            items = found
            break
    return [parse_review_element(item, asin, url) for item in items]


def parse_reviews_from_html(html: str, asin: str, url: str = "") -> list[RawReview]:
    """便捷入口：从 HTML 字符串直接解析评论（离线单测用）。"""
    url = url or product_url(asin)
    return parse_reviews(make_soup(html), asin, url)


def extract_global_rating_count(soup: BeautifulSoup) -> Optional[str]:
    """页面上显示的「总共 N 条评分」文案（诊断用）。"""
    for selector in (
        '[data-hook="cr-filter-info-review-rating-count"]',
        "#acrCustomerReviewText",
        '[data-hook="total-review-count"]',
    ):
        text = _text_of(_select_one(soup, selector))
        if text:
            return text.strip()
    return None


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #

def _select_one(element: Any, selector: str) -> Any:
    try:
        return element.select_one(selector)
    except Exception:  # noqa: BLE001
        return None


def _text_of(node: Any) -> str:
    if node is None:
        return ""
    try:
        return node.get_text(" ", strip=True)
    except Exception:  # noqa: BLE001
        try:
            return str(node).strip()
        except Exception:  # noqa: BLE001
            return ""


def _iter_texts(element: Any) -> list[str]:
    try:
        return [t.strip() for t in element.stripped_strings if t and t.strip()]
    except Exception:  # noqa: BLE001
        return []


def _extract_review_id(element: Any) -> str:
    """多来源兜底抽取 review_id（商品页 ``data-reviewid``；评论页容器 id）。"""
    attrs = getattr(element, "attrs", {}) or {}
    candidates = [
        attrs.get("data-reviewid", ""),
        attrs.get("id", ""),
        attrs.get("data-csa-c-slot-id", ""),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        candidate = str(candidate)
        match = _REVIEW_ID_RE.search(candidate) or _REVIEW_ID_ALT_RE.search(candidate)
        if match:
            return match.group(1)
    return ""


def _extract_title(element: Any) -> str:
    node = _select_one(element, '[data-hook="review-title"]')
    titles: list[str] = []
    if node is not None:
        titles = _iter_texts(node)
    if not titles:
        # 商品页 Top reviews：标题在 <h5> 内。
        for h5 in _select_all(element, "h5"):
            titles.extend(_iter_texts(h5))
            if titles:
                break
    titles = [t for t in titles if "out of 5 stars" not in t.lower()]
    return titles[-1] if titles else ""


def _extract_body(element: Any) -> str:
    for selector in ('[data-hook="review-body"]', '[data-hook="reviewText"]'):
        node = _select_one(element, selector)
        if node is None:
            continue
        parts = _iter_texts(node)
        if parts:
            return " ".join(parts)
    return ""


def _extract_variant(element: Any) -> Optional[str]:
    strip = _text_of(_select_one(element, '[data-hook="format-strip"]'))
    if strip:
        return strip or None
    for text in _iter_texts(element):
        if _VARIANT_RE.match(text):
            return text
    return None


def _select_all(element: Any, selector: str) -> list[Any]:
    try:
        return list(element.select(selector))
    except Exception:  # noqa: BLE001
        return []


def _to_iso_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    # 已是 ISO 形式
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    try:
        from dateutil import parser as _dateparser

        return _dateparser.parse(raw, fuzzy=True).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001 - 无法解析则返回空
        return ""


# --------------------------------------------------------------------------- #
# 薄抓取层（默认且唯一实现）
# --------------------------------------------------------------------------- #

class ScraplingAmazonUkFetcher:
    """基于 Scrapling 纯 HTTP ``Fetcher`` 的 Amazon UK 抓取器。

    口径：``impersonate='chrome'`` + ``stealthy_headers=True`` + ``timeout=30``，
    **无浏览器 / 无代理 / 无登录 / 无翻页**（探针已实测：200、无验证码、3/3 一致）。

    ``scrapling`` 惰性导入：本类实例化与 ``version`` 访问不触发导入；仅
    ``fetch_reviews`` 真正发起网络请求时才导入。故单元测试无需 scrapling。
    """

    version: str = config.FETCHER_VERSION

    def __init__(self, *, timeout_s: int | None = None, request_limit: int | None = None) -> None:
        self._timeout_s = timeout_s if timeout_s is not None else config.FETCH_PAGE_TIMEOUT_S
        self._request_limit = request_limit if request_limit is not None else config.FETCH_REQUEST_LIMIT

    def fetch_reviews(self, asin: str, limit: int) -> tuple[list[RawReview], FetchReport]:
        """抓取单个 ASIN 的商品页并解析「Top reviews」挂件（首屏口径）。

        本方法只做**一次** GET（最小可用）；重试 / 退避 / 换 ASIN 池 / 落盘由编排层
        ``AmazonUkRun`` 负责 —— 这样"抓取口径"与"编排策略"各自可测、互不缠绕。
        """
        url = product_url(asin)
        effective_limit = limit if limit and limit > 0 else self._request_limit
        report = FetchReport(
            asin=asin,
            requested=effective_limit,
            fetched=0,
            platform_cap=config.PLATFORM_CAP_PER_ASIN,
            ok=False,
            attempts=1,
            fetcher_version=self.version,
            swapped_from=None,
            error="",
        )

        try:
            page = self._get(url)
        except Exception as exc:  # noqa: BLE001 - 网络异常如实落进 report
            report.error = f"fetch_failed: {type(exc).__name__}: {exc}"
            return [], report

        html = html_of(page)
        status = getattr(page, "status", None)

        blocked, marker = detect_block(html)
        if blocked:
            report.error = f"blocked: {marker}"
            return [], report

        reviews = parse_reviews_from_html(html, asin, url)
        if effective_limit and effective_limit > 0:
            reviews = reviews[:effective_limit]

        report.fetched = len(reviews)
        report.ok = len(reviews) >= config.MIN_REVIEWS_PER_ASIN
        if not reviews:
            report.error = f"no_reviews_parsed (status={status})"
        return reviews, report

    # ---- 内部 ----
    def _get(self, url: str) -> Any:
        # 惰性导入：不在模块顶层引入 scrapling，保证离线解析与单测可跑。
        from scrapling.fetchers import Fetcher  # type: ignore[import-not-found]

        return Fetcher.get(
            url,
            impersonate="chrome",
            stealthy_headers=True,
            timeout=self._timeout_s,
        )


# --------------------------------------------------------------------------- #
# 编排层（T04）：重试 / 退避 / 换 ASIN 池 / 窗口截断 / fetch_report.json
# --------------------------------------------------------------------------- #
#
# 方案 B（用户已拍板，勿再变更）：**8–10 个 ASIN × 每 ASIN ~13 条**、纯 HTTP、不上登录态；
# 某 ASIN 失败或条数不足时**从备选池换一个 ASIN 重试**（不降条数、不转半自动）。
#
# 分工：
#   薄抓取层  —— 一次 GET + 解析（"能不能抓到"）
#   编排层    —— 重试多少次、等多久、换不换 ASIN、窗口外丢不丢（"抓到之后怎么算数"）

#: 命中这些前缀的错误视为**硬墙**（验证码 / 登录墙 / robot check）——
#: 立刻放弃该 ASIN，不做重试（§7：不硬刚），改从备选池换。
HARD_STOP_PREFIXES: tuple[str, ...] = (
    "blocked:",
    "captcha:",
    "login_wall:",
    "robot_check:",
    "signin:",
)


def is_hard_stop(error: str) -> bool:
    """该错误是否属于「不该重试」的硬墙（验证码 / 登录墙）。"""
    lowered = (error or "").strip().lower()
    return any(lowered.startswith(prefix) for prefix in HARD_STOP_PREFIXES)


@dataclass
class AsinOutcome:
    """一个**目标位**（slot）的最终结果（可能换过 ASIN）。

    ``captured`` 是**捕获条数**（含窗口外），``in_window`` 才是**真正落盘**的条数 ——
    两者分开，才能同时回答"抓全了吗"（对比 ``platform_cap``）与"有多少能用"。
    """

    slot: int
    requested_asin: str                 # 该位原本要的 ASIN
    asin: str                           # 最终取数的 ASIN（一般 == requested_asin）
    status: str                         # captured | swapped | failed
    ok: bool
    reviews: list[RawReview]            # **已按 24 个月窗口截断**
    report: FetchReport                 # 最后一次尝试的 report（含 attempts / swapped_from）
    captured: int
    in_window: int
    dropped_out_of_window: int
    attempts: int                       # 该位累计请求尝试次数（含换选后的）
    platform_cap: int
    error: str = ""

    @property
    def swapped_from(self) -> Optional[str]:
        return self.report.swapped_from

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "asin": self.asin,
            "requested_asin": self.requested_asin,
            "swapped_from": self.report.swapped_from,
            "status": self.status,
            "ok": self.ok,
            "requested": self.report.requested,
            "captured": self.captured,
            "in_window": self.in_window,
            "dropped_out_of_window": self.dropped_out_of_window,
            "platform_cap": self.platform_cap,
            # 「是否抓全」可判读：捕获条数 vs 平台上限 13
            "captured_vs_cap": f"{self.captured}/{self.platform_cap}",
            "attempts": self.attempts,
            "error": self.error or self.report.error,
        }


@dataclass
class FetchRun:
    """一次抓取运行的全部产出（内存态；落盘见 ``persist``）。"""

    outcomes: list[AsinOutcome] = field(default_factory=list)
    generated_at: str = ""
    fetcher_version: str = ""
    platform_cap: int = 13
    min_reviews_per_asin: int = 10
    time_window_months: int = 24
    targets: list[str] = field(default_factory=list)
    reserve_pool: list[str] = field(default_factory=list)

    # ---- 便捷视图 ----
    @property
    def reviews(self) -> list[RawReview]:
        """全部位次、窗口内的评论（去重交给 ``clean`` 层）。"""
        return [review for outcome in self.outcomes for review in outcome.reviews]

    @property
    def reports(self) -> list[FetchReport]:
        return [outcome.report for outcome in self.outcomes]

    @property
    def reserves_used(self) -> list[str]:
        return [o.asin for o in self.outcomes if o.swapped_from]

    def by_asin(self) -> dict[str, list[RawReview]]:
        """``{asin: [窗口内评论]}`` —— 供 CLI 逐 ASIN 落 ``raw_<asin>.json``。"""
        grouped: dict[str, list[RawReview]] = {}
        for outcome in self.outcomes:
            grouped.setdefault(outcome.asin, []).extend(outcome.reviews)
        return grouped

    def to_report_dict(self) -> dict[str, Any]:
        """``data/raw/fetch_report.json`` 的内容。"""
        captured_total = sum(o.captured for o in self.outcomes)
        in_window_total = sum(o.in_window for o in self.outcomes)
        dropped_total = sum(o.dropped_out_of_window for o in self.outcomes)
        used = {o.asin for o in self.outcomes}
        return {
            "generated_at": self.generated_at,
            "marketplace": config.MARKETPLACE,
            "fetcher_version": self.fetcher_version,
            "platform_cap_per_asin": self.platform_cap,
            "min_reviews_per_asin": self.min_reviews_per_asin,
            "time_window_months": self.time_window_months,
            "targets": list(self.targets),
            "reserve_pool": list(self.reserve_pool),
            "reserves_used": self.reserves_used,
            "reserve_pool_remaining": [a for a in self.reserve_pool if a not in used],
            "outcomes": [o.to_dict() for o in self.outcomes],
            "summary": {
                "slots": len(self.outcomes),
                "captured_slots": sum(1 for o in self.outcomes if o.status == "captured"),
                "swapped_slots": sum(1 for o in self.outcomes if o.status == "swapped"),
                "failed_slots": sum(1 for o in self.outcomes if o.status == "failed"),
                # 「抓全」的位次数：捕获条数达到平台上限
                "full_capture_slots": sum(
                    1 for o in self.outcomes if o.captured >= o.platform_cap
                ),
                "captured_total": captured_total,
                "in_window_total": in_window_total,
                "dropped_out_of_window_total": dropped_total,
                "attempts_total": sum(o.attempts for o in self.outcomes),
            },
        }

    def persist(
        self,
        *,
        raw_dir: str | Path | None = None,
        report_path: str | Path | None = None,
    ) -> list[Path]:
        """落盘：每个 ASIN 一个 ``raw_<asin>.json`` + 一份 ``fetch_report.json``。

        幂等（§7）：``raw_<asin>.json`` 按 ``review_id`` 去重后**整体覆盖**，不追加。
        """
        directory = Path(raw_dir) if raw_dir is not None else config.RAW_DIR
        report_file = Path(report_path) if report_path is not None else config.FETCH_REPORT_PATH
        directory.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        for asin, reviews in self.by_asin().items():
            if not reviews:
                continue
            written.append(
                write_raw_reviews(
                    asin, reviews, directory,
                    fetcher_version=self.fetcher_version,
                    fetched_at=self.generated_at,
                )
            )

        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(
            json.dumps(self.to_report_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(report_file)
        return written


def write_raw_reviews(
    asin: str,
    reviews: Sequence[RawReview],
    raw_dir: str | Path,
    *,
    fetcher_version: str = "",
    fetched_at: str = "",
) -> Path:
    """把单个 ASIN 的评论写成 ``raw_<asin>.json``（按 ``review_id`` 去重后覆盖）。

    ``review_id`` 为空（商品页缺 ``data-reviewid``）的条目**不参与去重** —— 它们本来就
    无法判别是否重复，交给 ``clean`` 层的 sha1 兜底。
    """
    seen: set[str] = set()
    unique: list[RawReview] = []
    for review in reviews:
        key = (review.review_id or "").strip()
        if key:
            if key in seen:
                continue
            seen.add(key)
        unique.append(review)

    payload = {
        "asin": asin,
        "marketplace": config.MARKETPLACE,
        "fetcher_version": fetcher_version,
        "fetched_at": fetched_at,
        "count": len(unique),
        "reviews": [review.to_dict() for review in unique],
    }
    path = Path(raw_dir) / f"raw_{asin}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


class AmazonUkRun:
    """一次抓取运行的编排：**重试 → 退避 → 换 ASIN → 窗口截断 → 报告**。

    串行、无翻页、无登录态（探针结论）。所有等待都走可注入的 ``sleeper``，
    因此单测能在**零等待**下覆盖重试/退避/换选全路径。

    :param fetcher: 任何满足 ``Fetcher`` Protocol 的实现（测试里可以是读本地 HTML 的桩）。
    :param targets: 目标位 ASIN 清单（顺序决定 ``slot``）。
    :param reserves: 备选池（FIFO 消费；与 ``targets`` 重复者自动跳过）。
    :param min_reviews: 单 ASIN 判"成功"的最低**窗口内**条数，默认 ``config.MIN_REVIEWS_PER_ASIN``。
    :param limit: 传给 ``fetch_reviews`` 的请求上限，默认 ``config.FETCH_REQUEST_LIMIT``。
    :param now: 时间窗基准（默认当前 UTC）——测试注入固定值以保证确定性。
    """

    def __init__(
        self,
        fetcher: Any,
        *,
        targets: Sequence[str],
        reserves: Sequence[str] = (),
        min_reviews: Optional[int] = None,
        limit: Optional[int] = None,
        time_window_months: Optional[int] = None,
        max_attempts: Optional[int] = None,
        min_delay_s: Optional[float] = None,
        max_delay_s: Optional[float] = None,
        backoff_factor: Optional[float] = None,
        sleeper: Optional[Callable[[float], None]] = None,
        jitter: Optional[Callable[[float, float], float]] = None,
        now: Optional[datetime] = None,
        generated_at: Optional[str] = None,
    ) -> None:
        self.fetcher = fetcher
        self.targets = [str(a).strip().upper() for a in targets if str(a).strip()]
        self.reserves = [str(a).strip().upper() for a in reserves if str(a).strip()]
        self.min_reviews = (
            min_reviews if min_reviews is not None else config.MIN_REVIEWS_PER_ASIN
        )
        self.limit = limit if limit is not None else config.FETCH_REQUEST_LIMIT
        self.time_window_months = (
            time_window_months if time_window_months is not None else config.TIME_WINDOW_MONTHS
        )
        self.max_attempts = max(1, max_attempts if max_attempts is not None else config.FETCH_MAX_ATTEMPTS)
        self.min_delay_s = min_delay_s if min_delay_s is not None else config.FETCH_MIN_DELAY_S
        self.max_delay_s = max_delay_s if max_delay_s is not None else config.FETCH_MAX_DELAY_S
        self.backoff_factor = (
            backoff_factor if backoff_factor is not None else config.FETCH_BACKOFF_FACTOR
        )
        self._sleep = sleeper if sleeper is not None else time.sleep
        self._jitter = jitter if jitter is not None else random.uniform
        self.now = now or datetime.now(timezone.utc)
        self.generated_at = generated_at or config.now_iso()
        #: ``[(kind, seconds)]`` —— 供测试与排障核对"等了多少、为什么等"。
        self.sleep_log: list[tuple[str, float]] = []

    # ------------------------------------------------------------------ #
    # 主流程
    # ------------------------------------------------------------------ #
    def fetch_all(self) -> FetchRun:
        """逐位抓取；每一位失败则从备选池换 ASIN 重试（不降条数）。"""
        run = FetchRun(
            generated_at=self.generated_at,
            fetcher_version=getattr(self.fetcher, "version", ""),
            platform_cap=config.PLATFORM_CAP_PER_ASIN,
            min_reviews_per_asin=self.min_reviews,
            time_window_months=self.time_window_months,
            targets=list(self.targets),
            reserve_pool=list(self.reserves),
        )

        used: set[str] = {asin.upper() for asin in self.targets}
        remaining_reserves = [
            asin for asin in self.reserves if asin.upper() not in used
        ]
        reserve_cursor = 0

        for slot, target in enumerate(self.targets):
            if slot > 0:
                self._sleep_between_slots()
            outcome, reserve_cursor = self._fetch_slot(
                slot, target, remaining_reserves, reserve_cursor, used
            )
            run.outcomes.append(outcome)

        return run

    # ------------------------------------------------------------------ #
    # 单个位次
    # ------------------------------------------------------------------ #
    def _fetch_slot(
        self,
        slot: int,
        target: str,
        reserves: list[str],
        cursor: int,
        used: set[str],
    ) -> tuple[AsinOutcome, int]:
        """抓一个位次：先试目标 ASIN，不行就按 FIFO 换备选，直到池子耗尽。"""
        requested_asin = target
        candidate: Optional[str] = target
        attempts_total = 0
        last_report: Optional[FetchReport] = None
        last_reviews: list[RawReview] = []
        last_error = ""

        while candidate is not None:
            reviews, report = self._attempt(candidate)
            attempts_total += report.attempts
            last_report, last_reviews = report, reviews

            kept, dropped = self._split_window(reviews)
            enough = report.error == "" and len(kept) >= self.min_reviews

            if enough:
                swapped = candidate != requested_asin
                report.swapped_from = requested_asin if swapped else None
                return AsinOutcome(
                    slot=slot, requested_asin=requested_asin, asin=candidate,
                    status="swapped" if swapped else "captured", ok=True,
                    reviews=kept, report=report,
                    captured=len(reviews), in_window=len(kept), dropped_out_of_window=dropped,
                    attempts=attempts_total, platform_cap=config.PLATFORM_CAP_PER_ASIN,
                    error="",
                ), cursor

            last_error = report.error or f"insufficient_reviews({len(kept)}<{self.min_reviews})"

            # 换 ASIN：FIFO 取下一个未用过的备选
            candidate = None
            while cursor < len(reserves):
                nxt = reserves[cursor]
                cursor += 1
                if nxt.upper() in used:
                    continue
                used.add(nxt.upper())
                candidate = nxt
                break

        # 池子耗尽：如实记为失败（**不降条数、不转半自动**）
        assert last_report is not None
        report = last_report
        report.swapped_from = (
            requested_asin if report.asin != requested_asin else report.swapped_from
        )
        kept, dropped = self._split_window(last_reviews)
        return AsinOutcome(
            slot=slot, requested_asin=requested_asin, asin=report.asin,
            status="failed", ok=False, reviews=kept, report=report,
            captured=len(last_reviews), in_window=len(kept), dropped_out_of_window=dropped,
            attempts=attempts_total, platform_cap=config.PLATFORM_CAP_PER_ASIN,
            error=last_error,
        ), cursor

    def _attempt(self, asin: str) -> tuple[list[RawReview], FetchReport]:
        """对一个 ASIN 做**请求级**重试 + 指数退避；命中硬墙立即收手。"""
        last_reviews: list[RawReview] = []
        last_report = FetchReport(
            asin=asin, requested=self.limit, fetched=0,
            platform_cap=config.PLATFORM_CAP_PER_ASIN, ok=False, attempts=0,
            fetcher_version=getattr(self.fetcher, "version", ""), error="not_attempted",
        )

        for attempt in range(1, self.max_attempts + 1):
            if attempt > 1:
                self._backoff(attempt)
            reviews, report = self.fetcher.fetch_reviews(asin, self.limit)
            report.attempts = attempt
            last_reviews, last_report = reviews, report

            if is_hard_stop(report.error):
                break                                    # 硬墙：不硬刚
            if report.error == "" and len(reviews) >= self.min_reviews:
                break                                    # 够数了
            # 否则继续重试（网络错误 / 解析为空 / 条数不足）
        return last_reviews, last_report

    # ------------------------------------------------------------------ #
    # 时间窗 / 限速
    # ------------------------------------------------------------------ #
    def _split_window(self, reviews: Sequence[RawReview]) -> tuple[list[RawReview], int]:
        """按 24 个月窗口切分：返回 ``(窗口内, 窗口外条数)``。

        ★ 窗口外评论**不落盘**（U6）：它们不会进 ``AsinOutcome.reviews``，
        自然也不会写进 ``raw_<asin>.json``，不会污染聚合分母。
        """
        kept: list[RawReview] = []
        dropped = 0
        for review in reviews:
            if config.within_window(
                review.review_date, now=self.now, months=self.time_window_months
            ):
                kept.append(review)
            else:
                dropped += 1
        return kept, dropped

    def _backoff(self, attempt: int) -> None:
        """指数退避 + 抖动：上界 = ``min(MAX, MIN × FACTOR^(attempt-2))``。"""
        upper = self.min_delay_s * (self.backoff_factor ** (attempt - 2))
        upper = min(self.max_delay_s, max(self.min_delay_s, upper))
        delay = self._jitter(self.min_delay_s, upper)
        self._record_sleep("retry", delay)
        self._sleep(delay)

    def _sleep_between_slots(self) -> None:
        """位次之间随机休眠（§7 限速：每 ASIN 之间 3–8s）。"""
        delay = self._jitter(self.min_delay_s, self.max_delay_s)
        self._record_sleep("slot", delay)
        self._sleep(delay)

    def _record_sleep(self, kind: str, delay: float) -> None:
        self.sleep_log.append((kind, float(delay)))

