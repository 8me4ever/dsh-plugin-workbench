#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Amazon UK 「餐盘碗碟」评论抓取可行性探针 (spike).

目的：以最小请求量证明「能否从 Amazon UK 拿到 plates & bowls 品类的商品页与评论」，
并逐级升级抓取强度（HTTP+TLS 指纹 -> 隐身浏览器 -> 动态浏览器），记录每一级的结果。

本脚本 *不是* 正式流水线，而是流水线抓取层的可行性证据来源：
它保存每一级的原始 HTML、解析结果与拦截判定，供后续正式抓取器复用成功配置。

用法（在安装了 scrapling[fetchers] 的 venv 里）：
    python probe_amazon_uk.py --step http_product
    python probe_amazon_uk.py --step stealth_product
    python probe_amazon_uk.py --step stealth_reviews
    python probe_amazon_uk.py --step stealth_reviews_p2
    python probe_amazon_uk.py --step dynamic_reviews
    python probe_amazon_uk.py --step markdown_test
    python probe_amazon_uk.py --step stability

每一步都会把结果追加到 probe/artifacts/steps.jsonl，并保存原始 HTML。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# --------------------------------------------------------------------------- #
# 配置：目标 ASIN 与 URL
# --------------------------------------------------------------------------- #

# 主目标 ASIN：Amazon Basics 6-Piece White Dinner Plate Set, 10.5 inches。
# 选取理由见 probe/REPORT.md —— 它是 Amazon UK「Plates」子类目的头部在售款
# （第三方 UK 选品数据源 flank.com 的 Amazon UK "Plates" 页将其列为 Top 1，
# 含 UK 定价与评论数），评论基数大，适合用于测试翻页上限。
DEFAULT_ASIN = "B0157FD9MS"

MARKETPLACE = "amazon.co.uk"
BASE = "https://www.amazon.co.uk"

PROBE_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = PROBE_DIR / "artifacts"
STEPS_LOG = ARTIFACT_DIR / "steps.jsonl"

ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# Amazon 反爬拦截页特征串
BLOCK_MARKERS = [
    "Enter the characters you see below",
    "Type the characters you see in this image",
    "Sorry, we just need to make sure you're not a robot",
    "api-services-support@amazon.com",
    "validateCaptcha",
    "To discuss automated access to Amazon data please contact",
    "Bots are not allowed",
    "Sorry! Something went wrong on our end",  # 不一定是拦截，但值得记录
    "Robot Check",
]

# 正常商品页特征
PRODUCT_MARKERS = ["id=\"productTitle\"", "id='productTitle'", "id=\"dp\"", "data-hook=\"review\""]

# 评论元素选择器（Amazon 有新旧两套 DOM，全部尝试）
REVIEW_ITEM_SELECTORS = [
    '[data-hook="review"]',
    'li[data-hook="review"]',
    'div[data-hook="review"]',
    '#cm_cr-review_list [data-hook="review"]',
]


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def product_url(asin: str) -> str:
    return f"{BASE}/dp/{asin}"


def reviews_url(asin: str, page: int = 1) -> str:
    url = f"{BASE}/product-reviews/{asin}/"
    if page > 1:
        url += f"?pageNumber={page}&reviewerType=all_reviews"
    return url


def html_of(page: Any) -> str:
    """尽力从 Response/Selector 里取出 HTML 字符串。"""
    try:
        return str(page.html_content)
    except Exception:
        pass
    try:
        body = page.body
        if isinstance(body, bytes):
            return body.decode("utf-8", "replace")
        return str(body)
    except Exception:
        return ""


def detect_block(html: str) -> tuple[bool, Optional[str]]:
    """检测是否命中反爬拦截页。返回 (是否被拦, 命中的特征串)。"""
    low = html.lower()
    for marker in BLOCK_MARKERS:
        if marker.lower() in low:
            # "Sorry! Something went wrong on our end" 单独出现不算硬拦截，但也记录
            return True, marker
    return False, None


def detect_product(html: str) -> bool:
    return any(m in html for m in PRODUCT_MARKERS)


def save_artifact(name: str, content: str) -> str:
    path = ARTIFACT_DIR / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def first_text(el: Any, selector: str) -> Optional[str]:
    """取 selector 命中的第一个元素的文本。"""
    try:
        got = el.css(selector)
        if got is None:
            return None
        if hasattr(got, "get"):
            val = got.get()
            if val:
                return str(val).strip()
        # 若返回列表
        try:
            items = list(got)
            if items:
                return str(items[0]).strip()
        except TypeError:
            pass
    except Exception:
        return None
    return None


def parse_reviews(page: Any) -> list[dict[str, Any]]:
    """从页面解析评论列表。返回记录列表（字段缺失填 None）。"""
    reviews: list[dict[str, Any]] = []
    items = None
    used_selector = None
    for sel in REVIEW_ITEM_SELECTORS:
        try:
            got = page.css(sel)
        except Exception:
            continue
        if got:
            try:
                lst = list(got)
            except TypeError:
                lst = []
            if lst:
                items = lst
                used_selector = sel
                break

    if not items:
        return []

    for el in items:
        rec: dict[str, Any] = {
            "review_id": None,
            "rating": None,
            "title": None,
            "body": None,
            "review_date": None,
            "review_country": None,
            "helpful_votes": None,
            "verified_purchase": None,
            "variant": None,
        }

        # review_id：多来源兜底。
        #  - 商品页：reviewContainer 上 data-reviewid="RU77ORJODNV3R"
        #  - 独立评论页：容器 id="review-XXX" / data-csa-c-slot-id="customer_review-XXX"
        try:
            attrib = el.attrib
            candidates = [
                attrib.get("data-reviewid", "") or "",
                attrib.get("id", "") or "",
                attrib.get("data-csa-c-slot-id", "") or "",
            ]
            for cand in candidates:
                if not cand:
                    continue
                m = re.search(r"(R[A-Z0-9]{8,})", cand) or re.search(r"(?:review|customer_review)-([A-Za-z0-9]+)", cand)
                if m:
                    rec["review_id"] = m.group(1)
                    break
        except Exception:
            pass

        # rating
        rating_text = (
            first_text(el, '[data-hook="review-star-rating"] .a-icon-alt::text')
            or first_text(el, '[data-hook="review-star-rating-view-point"] .a-icon-alt::text')
            or first_text(el, '[data-hook="cmps-review-star-rating"]::text')
            or first_text(el, ".review-rating .a-icon-alt::text")
            or first_text(el, "i.a-icon-star .a-icon-alt::text")
            or first_text(el, "i.a-icon-star span.a-icon-alt::text")
        )
        if rating_text:
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*out of\s*5", rating_text)
            if m:
                try:
                    rec["rating"] = float(m.group(1))
                except ValueError:
                    pass

        # title：
        #  - 独立评论页：[data-hook="review-title"]
        #  - 商品页 Top reviews：<h5 class="_Y3Itd_...">
        try:
            title_texts: list[str] = []
            for sel in ['[data-hook="review-title"]::text', "h5 ::text", "h5::text"]:
                got = el.css(sel)
                if got:
                    vals = got.getall() if hasattr(got, "getall") else [str(got)]
                    title_texts.extend([v.strip() for v in vals if v and v.strip()])
                if title_texts:
                    break
            title_texts = [t for t in title_texts if "out of 5 stars" not in t.lower()]
            if title_texts:
                rec["title"] = title_texts[-1]
        except Exception:
            pass

        # body：
        #  - 独立评论页：data-hook="review-body"
        #  - 商品页 Top reviews：data-hook="reviewText"
        try:
            body_texts: list[str] = []
            for sel in ['[data-hook="review-body"]', '[data-hook="reviewText"]']:
                got = el.css(sel)
                if got:
                    vals = got.css("::text").getall() if hasattr(got, "css") else []
                    body_texts = [t.strip() for t in vals if t and t.strip()]
                if body_texts:
                    break
            if body_texts:
                rec["body"] = " ".join(body_texts)
        except Exception:
            pass

        # date + country：形如 "Reviewed in the United Kingdom on 3 November 2025"
        date_text = first_text(el, '[data-hook="review-date"]::text')
        if date_text:
            rec["review_date"] = date_text
            m = re.search(r"Reviewed in (?:the )?(.+?) on (.+)$", date_text)
            if m:
                rec["review_country"] = m.group(1).strip()

        # helpful votes
        hv = first_text(el, '[data-hook="helpful-vote-statement"]::text')
        if hv:
            m = re.search(r"([0-9,]+)", hv)
            if m:
                try:
                    rec["helpful_votes"] = int(m.group(1).replace(",", ""))
                except ValueError:
                    pass
            elif "one person" in hv.lower():
                rec["helpful_votes"] = 1

        # verified purchase
        try:
            avp = el.css('[data-hook="avp-badge"]')
            rec["verified_purchase"] = bool(avp)
        except Exception:
            pass

        # variant（颜色/尺寸/套装）：format-strip 或含 "Colour:"/"Size:" 的行
        vt = first_text(el, '[data-hook="format-strip"]::text')
        if vt:
            rec["variant"] = vt
        else:
            try:
                raw = el.css("::text").getall()
                for t in raw:
                    tt = t.strip()
                    if re.match(r"^(Colour|Color|Size|Style|Flavour|Pattern)\s*:", tt):
                        rec["variant"] = tt
                        break
            except Exception:
                pass

        reviews.append(rec)

    # 记录实际生效的选择器
    if reviews:
        reviews[0]["_used_selector"] = used_selector
    return reviews


def summarize_reviews(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """统计字段可提取情况。"""
    if not reviews:
        return {"count": 0, "fields_present": {}, "sample": []}

    fields = ["review_id", "rating", "title", "body", "review_date",
              "review_country", "helpful_votes", "verified_purchase", "variant"]
    present = {}
    for f in fields:
        present[f] = sum(1 for r in reviews if r.get(f) not in (None, ""))
    sample = []
    for r in reviews[:3]:
        sample.append({k: v for k, v in r.items() if not k.startswith("_")})
    return {"count": len(reviews), "fields_present": present, "sample": sample}


def global_rating_count(page: Any) -> Optional[str]:
    """页面上显示的"总共 N 条评分"文案。"""
    for sel in [
        '[data-hook="cr-filter-info-review-rating-count"]::text',
        '#acrCustomerReviewText::text',
        '[data-hook="total-review-count"]::text',
    ]:
        t = first_text(page, sel)
        if t:
            return t.strip()
    return None


def record(step: str, payload: dict[str, Any]) -> None:
    """把一步的结果追加到 steps.jsonl 并打印简洁摘要。"""
    payload = {"step": step, "at": _now_iso(), **payload}
    with STEPS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print("=== STEP RESULT ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("=== END STEP RESULT ===")


# --------------------------------------------------------------------------- #
# 各级抓取
# --------------------------------------------------------------------------- #

def run_http_product(asin: str) -> None:
    """第 1 级：纯 HTTP + curl_cffi TLS 指纹伪装。"""
    from scrapling.fetchers import Fetcher

    url = product_url(asin)
    step = "L1_http_product"
    try:
        page = Fetcher.get(url, impersonate="chrome", stealthy_headers=True, timeout=30)
        html = html_of(page)
        blocked, marker = detect_block(html)
        save_artifact(f"{step}_{asin}.html", html)
        record(step, {
            "fetcher": "Fetcher.get(impersonate='chrome', stealthy_headers=True)",
            "url": url,
            "http_status": getattr(page, "status", None),
            "html_len": len(html),
            "blocked": blocked,
            "block_marker": marker,
            "looks_like_product": detect_product(html),
            "review_count_on_page": len(parse_reviews(page)),
        })
    except Exception as exc:  # noqa: BLE001
        record(step, {"url": url, "error": f"{type(exc).__name__}: {exc}",
                      "trace": traceback.format_exc()[-1500:]})


def run_http_reviews(asin: str, page_num: int = 1) -> None:
    """第 1 级续：纯 HTTP + TLS 指纹抓独立评论页。"""
    from scrapling.fetchers import Fetcher

    url = reviews_url(asin, page_num)
    step = f"L1_http_reviews_p{page_num}"
    try:
        page = Fetcher.get(url, impersonate="chrome", stealthy_headers=True, timeout=30)
        html = html_of(page)
        blocked, marker = detect_block(html)
        reviews = parse_reviews(page)
        save_artifact(f"{step}_{asin}.html", html)
        login_wall = bool(re.search(r"ap_signin|/ap/signin|Sign in", html)) and len(reviews) == 0
        record(step, {
            "fetcher": "Fetcher.get(impersonate='chrome', stealthy_headers=True)",
            "url": url,
            "page_number": page_num,
            "http_status": getattr(page, "status", None),
            "html_len": len(html),
            "blocked": blocked,
            "block_marker": marker,
            "login_wall_suspected": login_wall,
            "rating_count_text": global_rating_count(page),
            "review_count_on_page": len(reviews),
            "reviews": summarize_reviews(reviews),
        })
    except Exception as exc:  # noqa: BLE001
        record(step, {"url": url, "page_number": page_num,
                      "error": f"{type(exc).__name__}: {exc}",
                      "trace": traceback.format_exc()[-1500:]})


def run_http_reviews_p2(asin: str) -> None:
    run_http_reviews(asin, 2)


def run_http_mobile_dp(asin: str) -> None:
    """第 1 级续：纯 HTTP 抓移动端商品页（移动端评论列表历史上更易匿名访问）。"""
    from scrapling.fetchers import Fetcher

    url = f"{BASE}/gp/aw/d/{asin}"
    step = "L1_http_mobile_dp"
    try:
        page = Fetcher.get(url, impersonate="chrome", stealthy_headers=True, timeout=30)
        html = html_of(page)
        blocked, marker = detect_block(html)
        reviews = parse_reviews(page)
        save_artifact(f"{step}_{asin}.html", html)
        record(step, {
            "fetcher": "Fetcher.get(impersonate='chrome')",
            "url": url,
            "http_status": getattr(page, "status", None),
            "html_len": len(html),
            "blocked": blocked,
            "block_marker": marker,
            "login_wall_suspected": bool(re.search(r"ap_signin|/ap/signin", html)) and len(reviews) == 0,
            "review_count_on_page": len(reviews),
            "reviews": summarize_reviews(reviews),
        })
    except Exception as exc:  # noqa: BLE001
        record(step, {"url": url, "error": f"{type(exc).__name__}: {exc}",
                      "trace": traceback.format_exc()[-1500:]})


def run_medley_ajax(asin: str) -> None:
    """尝试商品页的 medley-reviews AJAX 端点（无需登录即可加载更多评论？）。"""
    from scrapling.fetchers import Fetcher, FetcherSession

    step = "L1_medley_ajax"
    product = product_url(asin)
    try:
        with FetcherSession(impersonate="chrome") as session:
            page = session.get(product, stealthy_headers=True, timeout=30)
            html = html_of(page)
            m = re.search(r'id="cr-state-object"\s+data-state=\'(.*?)\'', html, re.S)
            if not m:
                record(step, {"error": "cr-state-object not found; cannot get csrf token"})
                return
            state = json.loads(m.group(1).replace("&quot;", '"'))
            token = state.get("reviewsCsrfToken") or state.get("lazyWidgetCsrfToken")
            # 官方评论分页 AJAX 端点（历史用法，参考 xbyte / devhide 示例）
            ajax_url = "https://www.amazon.co.uk/hz/reviews-render/ajax/reviews/get/"
            payload = {
                "sortBy": "",
                "reviewerType": "all_reviews",
                "formatType": "",
                "mediaType": "",
                "filterByStar": "",
                "filterByAge": "",
                "pageNumber": "1",
                "filterByLanguage": "",
                "filterByKeyword": "",
                "shouldAppend": "undefined",
                "deviceType": "desktop",
                "canShowIntHeader": "undefined",
                "reftag": "cm_cr_arp_d_paging_btm_next_2",
                "pageSize": "10",
                "asin": asin,
            }
            resp = session.post(
                ajax_url,
                data=payload,
                headers={
                    "referer": f"{BASE}/product-reviews/{asin}/?ie=UTF8&reviewerType=all_reviews",
                    "x-requested-with": "XMLHttpRequest",
                    "anti-csrftoken-a2z": token or "",
                    "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "accept": "text/html,*/*",
                },
                timeout=30,
            )
            body = resp.body.decode("utf-8", "replace") if isinstance(resp.body, bytes) else str(resp.body)
            save_artifact(f"{step}_{asin}.txt", body)
            parsed = parse_reviews(resp)
            record(step, {
                "url": ajax_url,
                "http_status": getattr(resp, "status", None),
                "resp_len": len(body),
                "body_head": body[:600],
                "review_count_in_response": len(parsed),
                "reviews": summarize_reviews(parsed),
            })
    except Exception as exc:  # noqa: BLE001
        record(step, {"error": f"{type(exc).__name__}: {exc}",
                      "trace": traceback.format_exc()[-2000:]})


def run_http_custom(asin: str, url: str) -> None:
    """通用：纯 HTTP 抓任意 URL。"""
    from scrapling.fetchers import Fetcher

    step = "L1_http_custom"
    try:
        page = Fetcher.get(url, impersonate="chrome", stealthy_headers=True, timeout=30)
        html = html_of(page)
        blocked, marker = detect_block(html)
        reviews = parse_reviews(page)
        save_artifact(f"{step}_{abs(hash(url)) % 10**8}.html", html)
        record(step, {
            "fetcher": "Fetcher.get(impersonate='chrome')",
            "url": url,
            "http_status": getattr(page, "status", None),
            "html_len": len(html),
            "blocked": blocked,
            "block_marker": marker,
            "review_count_on_page": len(reviews),
            "reviews": summarize_reviews(reviews),
        })
    except Exception as exc:  # noqa: BLE001
        record(step, {"url": url, "error": f"{type(exc).__name__}: {exc}",
                      "trace": traceback.format_exc()[-1500:]})


def run_stealth_custom(asin: str, url: str) -> None:
    """通用：隐身浏览器抓任意 URL。"""
    from scrapling.fetchers import StealthyFetcher

    step = "L2_stealth_custom"
    try:
        page = StealthyFetcher.fetch(
            url, headless=True, network_idle=True, timeout=60000, wait=1500,
            locale="en-GB", timezone_id="Europe/London",
        )
        html = html_of(page)
        blocked, marker = detect_block(html)
        reviews = parse_reviews(page)
        save_artifact(f"{step}_{abs(hash(url)) % 10**8}.html", html)
        record(step, {
            "fetcher": "StealthyFetcher.fetch(headless=True, network_idle=True)",
            "url": url,
            "http_status": getattr(page, "status", None),
            "html_len": len(html),
            "blocked": blocked,
            "block_marker": marker,
            "login_wall_suspected": bool(re.search(r"ap_signin|/ap/signin", html)) and len(reviews) == 0,
            "review_count_on_page": len(reviews),
            "reviews": summarize_reviews(reviews),
        })
    except Exception as exc:  # noqa: BLE001
        record(step, {"url": url, "error": f"{type(exc).__name__}: {exc}",
                      "trace": traceback.format_exc()[-1500:]})


def run_stealth_product(asin: str) -> None:
    """第 2 级：隐身浏览器抓商品页。"""
    from scrapling.fetchers import StealthyFetcher

    url = product_url(asin)
    step = "L2_stealth_product"
    try:
        page = StealthyFetcher.fetch(
            url,
            headless=True,
            network_idle=True,
            timeout=60000,
            wait=1500,
            locale="en-GB",
            timezone_id="Europe/London",
        )
        html = html_of(page)
        blocked, marker = detect_block(html)
        reviews = parse_reviews(page)
        save_artifact(f"{step}_{asin}.html", html)
        record(step, {
            "fetcher": "StealthyFetcher.fetch(headless=True, network_idle=True, locale=en-GB)",
            "url": url,
            "http_status": getattr(page, "status", None),
            "html_len": len(html),
            "blocked": blocked,
            "block_marker": marker,
            "looks_like_product": detect_product(html),
            "rating_count_text": global_rating_count(page),
            "review_count_on_page": len(reviews),
            "reviews": summarize_reviews(reviews),
        })
    except Exception as exc:  # noqa: BLE001
        record(step, {"url": url, "error": f"{type(exc).__name__}: {exc}",
                      "trace": traceback.format_exc()[-1500:]})


def _stealth_reviews_generic(asin: str, page_num: int, step: str, label: str) -> None:
    from scrapling.fetchers import StealthyFetcher

    url = reviews_url(asin, page_num)
    try:
        page = StealthyFetcher.fetch(
            url,
            headless=True,
            network_idle=True,
            timeout=60000,
            wait=1500,
            locale="en-GB",
            timezone_id="Europe/London",
        )
        html = html_of(page)
        blocked, marker = detect_block(html)
        reviews = parse_reviews(page)
        save_artifact(f"{step}_{asin}.html", html)
        # 是否有登录墙
        login_wall = bool(re.search(r'(ap_signin|/ap/signin|Sign in|signin)', html)) and len(reviews) == 0
        record(step, {
            "fetcher": label,
            "url": url,
            "page_number": page_num,
            "http_status": getattr(page, "status", None),
            "html_len": len(html),
            "blocked": blocked,
            "block_marker": marker,
            "login_wall_suspected": login_wall,
            "rating_count_text": global_rating_count(page),
            "review_count_on_page": len(reviews),
            "reviews": summarize_reviews(reviews),
        })
    except Exception as exc:  # noqa: BLE001
        record(step, {"url": url, "page_number": page_num,
                      "error": f"{type(exc).__name__}: {exc}",
                      "trace": traceback.format_exc()[-1500:]})


def run_stealth_reviews(asin: str) -> None:
    """第 3 级：隐身浏览器抓独立评论页（第 1 页）。"""
    _stealth_reviews_generic(asin, 1, "L3_stealth_reviews_p1",
                             "StealthyFetcher.fetch(product-reviews p1)")


def run_stealth_reviews_p2(asin: str) -> None:
    """第 3 级续：隐身浏览器抓独立评论页（第 2 页），测试翻页。"""
    _stealth_reviews_generic(asin, 2, "L3_stealth_reviews_p2",
                             "StealthyFetcher.fetch(product-reviews p2)")


def run_dynamic_reviews(asin: str) -> None:
    """第 4 级：完整浏览器自动化抓评论页。"""
    from scrapling.fetchers import DynamicFetcher

    url = reviews_url(asin, 1)
    step = "L4_dynamic_reviews_p1"
    try:
        page = DynamicFetcher.fetch(
            url,
            headless=True,
            network_idle=True,
            timeout=60000,
            locale="en-GB",
        )
        html = html_of(page)
        blocked, marker = detect_block(html)
        reviews = parse_reviews(page)
        save_artifact(f"{step}_{asin}.html", html)
        record(step, {
            "fetcher": "DynamicFetcher.fetch(headless=True, network_idle=True)",
            "url": url,
            "http_status": getattr(page, "status", None),
            "html_len": len(html),
            "blocked": blocked,
            "block_marker": marker,
            "rating_count_text": global_rating_count(page),
            "review_count_on_page": len(reviews),
            "reviews": summarize_reviews(reviews),
        })
    except Exception as exc:  # noqa: BLE001
        record(step, {"url": url, "error": f"{type(exc).__name__}: {exc}",
                      "trace": traceback.format_exc()[-1500:]})


def run_markdown_test(asin: str) -> None:
    """验证 page.markdown() 的可用性与质量（在可访问的 HTTP 商品页上做）。"""
    from scrapling.fetchers import Fetcher

    url = product_url(asin)
    step = "MD_http_product_markdown"
    try:
        page = Fetcher.get(url, impersonate="chrome", stealthy_headers=True, timeout=30)
        md = page.markdown()
        save_artifact(f"{step}_{asin}.md", md)
        lines = [ln for ln in md.splitlines() if ln.strip()]
        short = sum(1 for ln in lines if len(ln.strip()) < 4)
        record(step, {
            "fetcher": "Fetcher.get(impersonate='chrome') + page.markdown()",
            "url": url,
            "md_char_len": len(md),
            "md_nonempty_lines": len(lines),
            "short_line_ratio": round(short / len(lines), 3) if lines else None,
            "contains_out_of_5": md.count("out of 5 stars"),
            "contains_review_text": "Brief content visible" in md or "Read more" in md,
            "preview_head": md[:1500],
        })
    except Exception as exc:  # noqa: BLE001
        record(step, {"url": url, "error": f"{type(exc).__name__}: {exc}",
                      "trace": traceback.format_exc()[-1500:]})


def run_stability(asin: str) -> None:
    """同一 HTTP 请求重复 3 次，检验稳定性（HTTP 是我们已验证可行的路径）。"""
    from scrapling.fetchers import Fetcher

    url = product_url(asin)
    step = "STABILITY_http_product_x3"
    runs = []
    for i in range(3):
        try:
            page = Fetcher.get(url, impersonate="chrome", stealthy_headers=True, timeout=30)
            html = html_of(page)
            blocked, marker = detect_block(html)
            runs.append({
                "run": i + 1,
                "http_status": getattr(page, "status", None),
                "html_len": len(html),
                "blocked": blocked,
                "block_marker": marker,
                "review_count_on_page": len(parse_reviews(page)),
            })
        except Exception as exc:  # noqa: BLE001
            runs.append({"run": i + 1, "error": f"{type(exc).__name__}: {exc}"})
        time.sleep(4)
    record(step, {"url": url, "runs": runs})


# 需要额外 --url 参数的步骤
URL_STEPS = {
    "http_custom": run_http_custom,
    "stealth_custom": run_stealth_custom,
}

STEPS = {
    "http_product": run_http_product,
    "http_reviews": run_http_reviews,
    "http_reviews_p2": run_http_reviews_p2,
    "http_mobile_dp": run_http_mobile_dp,
    "medley_ajax": run_medley_ajax,
    "stealth_product": run_stealth_product,
    "stealth_reviews": run_stealth_reviews,
    "stealth_reviews_p2": run_stealth_reviews_p2,
    "dynamic_reviews": run_dynamic_reviews,
    "markdown_test": run_markdown_test,
    "stability": run_stability,
    **URL_STEPS,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Amazon UK 评论抓取可行性探针")
    parser.add_argument("--step", required=True, choices=sorted(STEPS.keys()))
    parser.add_argument("--asin", default=DEFAULT_ASIN)
    parser.add_argument("--url", default=None, help="http_custom / stealth_custom 使用的 URL")
    args = parser.parse_args()

    if args.step in URL_STEPS:
        if not args.url:
            parser.error("该步骤需要 --url")
        STEPS[args.step](args.asin, args.url)
    else:
        STEPS[args.step](args.asin)
    return 0


if __name__ == "__main__":
    sys.exit(main())
