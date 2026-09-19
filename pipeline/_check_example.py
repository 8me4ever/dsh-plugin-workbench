"""One-off: assert data/analysis.example.json is internally self-consistent."""
from __future__ import annotations

import json
import math
from pathlib import Path

HITS_MIN, RATIO, FLOOR = 3, 0.3, 3
TOL = 3e-6


def close(a, b):
    return abs(a - b) <= TOL


def main():
    path = Path(__file__).resolve().parents[1] / "data" / "analysis.example.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    s = d["sample"]
    n = s["asins_with_data"]
    thr = max(FLOOR, math.ceil(RATIO * n))

    cu = s["comments_usable"]
    lf = d["data_quality"]["labeling_failures"]
    labeled = cu - lf
    assert close(round(labeled / cu, 6), s["labeled_coverage"]), (labeled / cu, s["labeled_coverage"])

    for row in s["per_asin"]:
        assert row["usable"] <= row["fetched"] <= 13, row

    for dim in d["dimensions"]:
        h = dim["hits"]
        if h == 0:
            assert dim["net_sat"] == 0 and dim["satisfaction"] == 0.5, dim
        else:
            pos = round(dim["pos_share"] * h)
            neg = round(dim["neg_share"] * h)
            assert close(pos / h, dim["pos_share"]), dim["id"]
            assert close(neg / h, dim["neg_share"]), dim["id"]
            assert close(round((pos - neg) / h, 6), dim["net_sat"]), (dim["id"], (pos - neg) / h, dim["net_sat"])
            assert close(round(((pos - neg) / h + 1) / 2, 6), dim["satisfaction"]), dim["id"]
            assert close(round(h / labeled, 6), dim["attention"]), (dim["id"], h / labeled, dim["attention"])
        assert dim["rankable"] == (h >= HITS_MIN and dim["asin_count"] >= thr), dim["id"]
        assert dim["low_confidence"] == (not dim["rankable"]), dim["id"]

    ranked = {x["id"]: x for x in d["dimensions"] if x["rankable"]}
    opp_ids = {o["dimension"] for o in d["opportunities"]}
    assert opp_ids <= set(ranked), (opp_ids, set(ranked))
    assert opp_ids.isdisjoint({"SCN", "SAF"}), opp_ids
    for o in d["opportunities"]:
        dim = ranked[o["dimension"]]
        assert close(round(o["attention"] * (1 - dim["satisfaction"]), 6), o["opportunity"]), o["dimension"]

    for row in d["by_asin"]:
        for dim_id, cell in row["dimensions"].items():
            assert dim_id in ranked, (row["asin"], dim_id)
            assert cell["hits"] >= 1, (row["asin"], dim_id)

    print(f"OK  labeled={labeled}/{cu}  thr={thr}  rankable={sorted(ranked)}  "
          f"low_conf={sorted(x['id'] for x in d['dimensions'] if not x['rankable'])}")


if __name__ == "__main__":
    main()
