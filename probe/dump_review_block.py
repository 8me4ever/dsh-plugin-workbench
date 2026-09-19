#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""离线 dump 商品页第一个 reviewContainer 区块与 cr-state-object，用于修正选择器。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main(path: Path) -> None:
    raw = path.read_text(encoding="utf-8", errors="replace")

    i = raw.find('data-hook="reviewContainer"')
    print("=== reviewContainer raw block (first) ===")
    if i >= 0:
        print(raw[i - 200:i + 2600])
    else:
        print("!! reviewContainer not found")

    print("\n=== cr-state-object data-state ===")
    m = re.search(r'id="cr-state-object"\s+data-state=\'(.*?)\'', raw, re.S)
    if m:
        print(m.group(1)[:1500])
    else:
        print("!! cr-state-object not found")

    print("\n=== count reviewContainer ===", raw.count('data-hook="reviewContainer"'))
    print("=== count a-profile-name ===", raw.count('a-profile-name'))
    print("=== body class candidates ===")
    for pat in ['review-text', 'data-hook="reviewText"', 'cr-original-review-text', 'review-text-content', 'a-expander-content reviewText']:
        print(f"   {pat}: {raw.count(pat)}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
