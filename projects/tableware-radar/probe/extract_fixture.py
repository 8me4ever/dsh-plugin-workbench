"""从探针真产物中抽取评论节点，生成**小而真实**的测试夹具（一次性脚本）。

``probe/artifacts/`` 被 .gitignore 忽略（体量大且可重跑），因此把 13 个真实评论节点
抽出来单独入库，让 T04 的离线测试在**全新 clone 上也能跑**。抽取出来的 markup 是**真货**，
不是编造数据。
"""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "probe" / "artifacts" / "L1_http_product_B0157FD9MS.html"
TARGET = REPO / "pipeline" / "tests" / "fixtures" / "amazon_uk_product_B0157FD9MS.html"

HTML = SOURCE.read_text(encoding="utf-8", errors="replace")
soup = BeautifulSoup(HTML, "html.parser")   # lxml 未必在环境里；html.parser 到处都有
nodes = soup.select('[data-hook="review"]')

assert len(nodes) == 13, f"期望 13 条，实得 {len(nodes)}"

body = "\n".join(str(node) for node in nodes)
document = (
    "<!DOCTYPE html>\n"
    '<html lang="en"><head><meta charset="utf-8">'
    "<title>Amazon UK product page — review nodes extracted from the probe artifact</title>"
    "</head>\n<body>\n"
    '<div id="dp"><h1 id="productTitle">Amazon Basics 6-Piece White Dinner Plate Set</h1></div>\n'
    '<div id="customerReviews">\n<div id="cm_cr-review_list">\n'
    f"{body}\n"
    "</div>\n</div>\n"
    "</body></html>\n"
)

TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_text(document, encoding="utf-8")
print(f"wrote {TARGET} ({TARGET.stat().st_size} bytes, {len(nodes)} review nodes)")
