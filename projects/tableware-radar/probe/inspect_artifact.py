#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""离线检查已保存的探针 HTML 产物：确认商品身份、评分数与字段抽取质量。

不发起任何网络请求（纯本地解析），用于给 REPORT.md 提供证据。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from scrapling.parser import Selector

from probe_amazon_uk import html_of, parse_reviews, summarize_reviews, global_rating_count, detect_block


def inspect(path: Path) -> None:
    raw = path.read_text(encoding="utf-8", errors="replace")
    page = Selector(raw, url="https://www.amazon.co.uk/")

    title = None
    for sel in ["#productTitle::text", "h1#title span::text", 'meta[name="title"]::attr(content)']:
        t = page.css(sel)
        try:
            v = t.get() if hasattr(t, "get") else None
        except Exception:
            v = None
        if v:
            title = str(v).strip()
            break

    blocked, marker = detect_block(raw)
    reviews = parse_reviews(page)

    print(f"FILE            : {path.name}")
    print(f"HTML_LEN        : {len(raw)}")
    print(f"BLOCKED         : {blocked} ({marker})")
    print(f"PRODUCT_TITLE   : {title}")
    print(f"RATING_COUNT_TXT: {global_rating_count(page)}")
    print(f"REVIEWS_PARSED  : {len(reviews)}")
    print("FIELD_COVERAGE  :", summarize_reviews(reviews)["fields_present"])
    # 判定 review 区块是否真的属于本 ASIN（避免抓到推荐位评论）
    asin_hits = len(re.findall(r"B0157FD9MS", raw))
    print(f"ASIN_MENTIONS   : {asin_hits}")
    print("--- first 2 reviews ---")
    for r in reviews[:2]:
        print({k: v for k, v in r.items() if not k.startswith("_")})


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: inspect_artifact.py <html-file>")
        raise SystemExit(1)
    inspect(Path(sys.argv[1]))
