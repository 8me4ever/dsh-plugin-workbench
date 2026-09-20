#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""调试：为什么 review_id 抽不到。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrapling.parser import Selector  # noqa: E402

raw = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
page = Selector(raw, url="https://www.amazon.co.uk/")

els = page.css('[data-hook="reviewContainer"]')
print("len(reviewContainer):", len(els))
first = list(els)[0]
print("type:", type(first))
print("attrib:", dict(first.attrib) if first.attrib else None)

inner = page.css('[data-hook="review"]')
print("\nlen(data-hook=review):", len(inner))
if inner:
    fi = list(inner)[0]
    print("inner attrib:", dict(fi.attrib) if fi.attrib else None)
