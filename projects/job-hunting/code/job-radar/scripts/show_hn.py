"""查看 HN 抓取结果(详情页增强后)。"""
import sys

sys.path.insert(0, ".")
from src.storage import Storage

s = Storage("data")
hn = [j for j in s.all_jobs() if j["source"] == "HN-Jobs"]
print(f"HN 共 {len(hn)} 条:")
for j in hn[:8]:
    print(f"  [{j['grade']}] {j['title'][:55]} | {j['company'][:20]} | 薪资:{j['salary_min']}-{j['salary_max']} | 城市:{j['city'] or '-'} | 评分:{j['score']}")
    if j["reasons"]:
        print(f"      原因:{j['reasons']}")
s.close()
