"""查看深圳 BOSS 岗位明细。"""
import sys
from collections import Counter

sys.path.insert(0, ".")
from src.storage import Storage

s = Storage("data")
jobs = s.all_jobs()
sz = [j for j in jobs if j["source"] == "boss" and j["city"] == "深圳"]
print(f"深圳 BOSS 岗位: {len(sz)} 条")
print("分级:", dict(Counter(j["grade"] for j in sz)))
sz_sorted = sorted(sz, key=lambda x: -x["score"])
print("\n== 深圳 Top 12 ==")
for j in sz_sorted[:12]:
    hits = j["details"].get("skill_hits", [])
    print(f"  [{j['grade']}] {j['score']:>5} | {j['title'][:30]} | {j['company'][:14]} | {j['salary_min']}-{j['salary_max']} | 命中:{','.join(hits[:4])}")
print("\n== 薪资 Top 5 ==")
for j in sorted(sz, key=lambda x: -x["salary_max"])[:5]:
    print(f"  {j['title'][:32]} | {j['company'][:16]} | {j['salary_min']}-{j['salary_max']}")
s.close()
