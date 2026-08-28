"""查看 BOSS 岗位入库后的分级分布。"""
import sys
from collections import Counter

sys.path.insert(0, ".")
from src.storage import Storage

s = Storage("data")
jobs = s.all_jobs()
boss = [j for j in jobs if j["source"] == "boss"]
print(f"BOSS 岗位: {len(boss)} 条")
print("分级:", dict(Counter(j["grade"] for j in boss)))
print("\n== S/A 级岗位 ==")
for j in boss:
    if j["grade"] in ("S", "A"):
        print(f"  [{j['grade']}] {j['title'][:35]} | {j['company'][:16]} | {j['salary_min']}-{j['salary_max']} | {j['score']}")
print("\n== C 级(被过滤)样本 ==")
c_list = [j for j in boss if j["grade"] == "C"]
for j in c_list[:3]:
    print(f"  [C] {j['title'][:35]} | {j['company'][:16]} | 原因:{j['reasons']}")
s.close()
