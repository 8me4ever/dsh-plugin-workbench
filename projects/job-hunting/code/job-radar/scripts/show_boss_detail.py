"""分析 BOSS 岗位评分分布与高分岗位明细。"""
import sys

sys.path.insert(0, ".")
from src.storage import Storage

s = Storage("data")
boss = [j for j in s.all_jobs() if j["source"] == "boss"]
boss.sort(key=lambda x: -x["score"])

print("== 评分 Top 12 ==")
for j in boss[:12]:
    detail = j["details"]
    print(f"  [{j['grade']}] {j['score']:>5} | {j['title'][:32]} | {j['company'][:14]} | 命中:{len(detail.get('skill_hits',[]))}个 | 明细skill={detail.get('skill')}, exp={detail.get('experience')}, company={detail.get('company')}, fresh={detail.get('freshness')}, commute={detail.get('commute')}, other={detail.get('other')}")

print("\n== 薪资 Top 5 ==")
for j in sorted(boss, key=lambda x: -x["salary_max"])[:5]:
    print(f"  {j['title'][:35]} | {j['company'][:14]} | {j['salary_min']}-{j['salary_max']}")
s.close()
