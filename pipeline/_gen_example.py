"""One-off: regenerate data/analysis.example.json from the real aggregate().

Not committed — run from the pipeline dir with PYTHONPATH=src:
    set PYTHONPATH=pipeline/src  &&  python pipeline/_gen_example.py
"""
from __future__ import annotations

import json

from tableware_radar import config
from tableware_radar.aggregate import aggregate
from tableware_radar.dimensions import DimensionSet
from tableware_radar.models import Dimension, FetchReport, Label, ReviewRecord

DIMS = [
    ("DUR", "耐用性", "结构与材质在长期使用/清洗后是否保持完好",
     ["chipped", "cracked", "warped", "durable_ok"], False),
    ("CLE", "易清洁", "清洁便利性（手洗/洗碗机）",
     ["easy_clean", "hard_clean", "dishwasher_safe"], False),
    ("AES", "美观度", "外观与质感是否讨喜",
     ["looks_good", "looks_cheap"], False),
    ("SIZ", "尺寸", "尺寸是否符合预期",
     ["size_fit", "size_small", "size_large"], False),
    ("PCK", "包装", "运输/包装完好度",
     ["well_packed", "damaged_in_transit"], False),
    ("SCN", "使用场景", "评论提及的使用场景切片",
     ["everyday_dining", "entertaining", "afternoon_tea", "roast_dinner",
      "gifting", "kids_family", "baking_serving"], True),
    ("STR", "强度/结构", "结构强度是否足够",
     ["sturdy", "flimsy"], False),
    ("HAN", "手感/握持", "手感与握持是否舒适",
     ["comfortable", "rough"], False),
    ("VAL", "性价比/安全", "性价比是否合理",
     ["good_value", "poor_value"], False),
    ("SAF", "合规/安全", "安全与合规相关声明",
     ["lead_free_claim", "food_grade"], True),
]
NAME = {d[0]: d[1] for d in DIMS}

TITLES = {
    "B0157FD9MS": "Amazon Basics 6-Piece White Dinner Plate Set",
    "B0EXAMPLE2": "Example Porcelain Bowl Set",
    "B0EXAMPLE3": "Example Stoneware Mug Set",
}

# Each ASIN ships exactly 13 records (the platform's首屏 cap), so `fetched` is
# honest and `usable <= fetched` always holds. DUR leads on negatives across all
# three ASINs; PCK/HAN/SIZ stay single-ASIN so a "n不足" row is real.
LABELED = {
    "B0157FD9MS": [
        ("DUR", "chipped", "neg", "one plate chipped after a few washes"),
        ("DUR", "cracked", "neg", "a hairline crack appeared near the rim"),
        ("DUR", "warped", "neg", "the plate warped slightly in the dishwasher"),
        ("CLE", "easy_clean", "pos", "wipes clean with a quick rinse"),
        ("CLE", "dishwasher_safe", "pos", "holds up fine in the dishwasher"),
        ("CLE", "hard_clean", "neg", "stains are hard to scrub off"),
        ("SCN", "everyday_dining", "neutral", "used it for everyday family dinners"),
        ("SCN", "entertaining", "neutral", "great for hosting guests"),
        ("AES", "looks_good", "pos", "looks elegant on the table"),
        ("VAL", "good_value", "pos", "good value for the price"),
        ("STR", "sturdy", "pos", "feels sturdy and solid"),
        ("PCK", "damaged_in_transit", "neg", "arrived with a chipped rim due to minimal packaging"),
        ("SAF", "lead_free_claim", "neutral", "advertised as lead-free"),
    ],
    "B0EXAMPLE2": [
        ("DUR", "chipped", "neg", "a plate chipped after a few weeks"),
        ("DUR", "cracked", "neg", "a crack formed along the edge"),
        ("DUR", "durable_ok", "pos", "survived months of daily use"),
        ("CLE", "easy_clean", "pos", "rinses clean easily"),
        ("CLE", "dishwasher_safe", "pos", "safe in the dishwasher"),
        ("CLE", "hard_clean", "neg", "grease is stubborn to remove"),
        ("SCN", "everyday_dining", "neutral", "everyday dinners at home"),
        ("SCN", "afternoon_tea", "neutral", "used for afternoon tea"),
        ("AES", "looks_good", "pos", "the glaze looks lovely"),
        ("VAL", "good_value", "pos", "cheap for the quality"),
        ("STR", "sturdy", "pos", "thick and solid"),
        ("HAN", "comfortable", "pos", "comfortable in the hand"),
    ],
    "B0EXAMPLE3": [
        ("DUR", "chipped", "neg", "one rim arrived chipped"),
        ("DUR", "durable_ok", "pos", "still intact after months"),
        ("DUR", "durable_ok", "pos", "no cracks so far"),
        ("CLE", "easy_clean", "pos", "cleans up in seconds"),
        ("CLE", "easy_clean", "pos", "very easy to wash"),
        ("CLE", "dishwasher_safe", "pos", "dishwasher friendly"),
        ("SCN", "entertaining", "neutral", "great for dinner parties"),
        ("SCN", "roast_dinner", "neutral", "used it for a roast dinner"),
        ("AES", "looks_good", "pos", "elegant design"),
        ("VAL", "good_value", "pos", "good value"),
        ("STR", "sturdy", "pos", "feels robust"),
        ("OTHER", "delivery packaging", "neutral", "delivery packaging could be sturdier"),
    ],
}

# The 13th record of each ASIN, and the flag that keeps the counts honest:
#   B0EXAMPLE2 -> a usable review whose labeling failed (raises the coverage
#                 denominator without touching any dimension);
#   B0EXAMPLE3 -> a review too short to be usable at all.
LABEL_FAIL_ASIN = "B0EXAMPLE2"
UNUSABLE_ASIN = "B0EXAMPLE3"

DATES = ["2025-03-11", "2025-05-02", "2025-07-19", "2025-09-30", "2026-01-08", "2026-04-22"]
RATINGS = [5, 4, 4, 3, 5, 4, 2, 5, 4, 3, 5, 4]


def build_dims() -> DimensionSet:
    ds = DimensionSet(version=config.DIMENSION_SET_VERSION)
    for dim_id, name, definition, values, excluded in DIMS:
        ds.by_id[dim_id] = Dimension(
            id=dim_id, name=name, definition=definition,
            judgement="由评论原文判定", values=list(values),
            positive_examples=["positive example"], negative_examples=["negative example"],
            excluded_from_opportunity=excluded,
        )
    return ds


def _label(spec):
    dim, value, polarity, evidence = spec
    return Label(dimension=dim, dimension_name=NAME.get(dim, "其他"), value=value,
                 polarity=polarity, confidence=0.9, evidence=evidence)


def _record(rid, asin, specs, *, usable=True, ok=True, rating=4, date="2025-06-01"):
    rec = ReviewRecord(review_id=rid, asin=asin)
    rec.content = {"is_usable": usable}
    rec.labeling = {"ok": ok}
    rec.raw = {"rating": rating, "review_date": date}
    rec.labels = [_label(s) for s in specs]
    return rec


def build_records():
    records = []
    for a_idx, asin in enumerate(TITLES):
        for i, spec in enumerate(LABELED[asin]):
            records.append(_record(
                f"{asin}-R{i:02d}", asin, [spec],
                rating=RATINGS[(i + a_idx) % len(RATINGS)],
                date=DATES[(i + a_idx) % len(DATES)]))
        if asin == LABEL_FAIL_ASIN:
            records.append(_record(f"{asin}-F0", asin, [], ok=False,
                                   rating=4, date="2025-11-01"))
        elif asin == UNUSABLE_ASIN:
            records.append(_record(f"{asin}-U0", asin, [], usable=False, ok=False,
                                   rating=5, date="2025-12-01"))
    return records


def build_reports(records):
    counts: dict[str, int] = {}
    for rec in records:
        counts[rec.asin] = counts.get(rec.asin, 0) + 1
    return [
        FetchReport(asin=asin, requested=config.FETCH_REQUEST_LIMIT,
                    fetched=counts.get(asin, 0), platform_cap=config.PLATFORM_CAP_PER_ASIN,
                    ok=counts.get(asin, 0) >= config.MIN_REVIEWS_PER_ASIN,
                    attempts=1, fetcher_version=config.FETCHER_VERSION)
        for asin in TITLES
    ]


def main():
    records = build_records()
    analysis = aggregate(
        records, build_dims(), reports=build_reports(records),
        titles=dict(TITLES), generated_at="2026-09-19T00:00:00Z")
    out = config.DATA_DIR / "analysis.example.json"
    out.write_text(json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
