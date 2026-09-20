#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""离线分析 Amazon 商品页 / 评论页 HTML 结构（不发网络请求）。

用于：
  1. 找出评论 DOM 的真实结构（修正字段抽取选择器）；
  2. 找 "See more reviews" 链接指向；
  3. 查是否存在无需登录的评论 AJAX 端点。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def show(label: str, pattern: str, raw: str, limit: int = 3, span: int = 220) -> None:
    hits = [m for m in re.finditer(pattern, raw)]
    print(f"--- {label} : {len(hits)} hit(s)")
    for m in hits[:limit]:
        s = max(0, m.start() - 40)
        print("   ...", raw[s:m.start() + span].replace("\n", " ")[:span + 40], "...")
    print()


def main(path: Path) -> None:
    raw = path.read_text(encoding="utf-8", errors="replace")
    print(f"FILE = {path.name}  (len={len(raw)})\n")

    show("show_all_reviews_link", r'id="cm_cr_dp_d_show_all_btm"', raw, limit=2, span=300)
    show("see_all_href", r'href="[^"]*#customerReviews[^"]*"', raw, limit=2, span=200)
    show("review_list_container", r'id="cm_cr-review_list"', raw, limit=1, span=200)
    show("dp_review_container", r'id="cm-cr-dp-review-list"', raw, limit=1, span=200)
    show("review_body_hook", r'data-hook="review-body"', raw, limit=1, span=320)
    show("review_title_hook", r'data-hook="review-title"', raw, limit=1, span=320)
    show("review_id_attr", r'id="(?:review|customer_review)-[A-Z0-9]+"', raw, limit=3, span=60)
    show("reviews_render_ajax", r'reviews-render/ajax', raw, limit=3, span=200)
    show("cr_medley", r'"cr-widget|medley|reviews-render', raw, limit=5, span=120)
    show("signin_wall", r'ap/signin', raw, limit=2, span=120)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
