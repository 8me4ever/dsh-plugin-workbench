"""直接抓深圳 BOSS 岗位(独立脚本,带完整浏览器头,单次请求)。"""
import json
import sys
import time
from urllib.parse import quote

sys.path.insert(0, "scripts")
from playwright.sync_api import sync_playwright
from boss import api_headers, SEARCH_API, to_job_dict

CITY_SHENZHEN = "101280600"
QUERY = "数据分析"


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir="data/.boss_profile", headless=True,
        )
        req = ctx.request
        all_jobs = []
        for page in range(1, 3):
            params = {
                "scene": "1", "query": QUERY, "city": CITY_SHENZHEN,
                "page": str(page), "pageSize": "30",
            }
            try:
                r = req.get(SEARCH_API, params=params, headers=api_headers(QUERY, CITY_SHENZHEN), timeout=30000)
                data = r.json()
                code = data.get("code")
                print(f"第{page}页 code={code} msg={data.get('message')}", flush=True)
                if code != 0:
                    break
                jobs = data.get("zpData", {}).get("jobList", [])
                all_jobs.extend(jobs)
                print(f"  本页 {len(jobs)} 条", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"第{page}页异常: {str(e)[:120]}", flush=True)
            time.sleep(3)
        ctx.close()

    print(f"共 {len(all_jobs)} 条", flush=True)
    if all_jobs:
        # 落盘
        import pathlib
        data_dir = pathlib.Path("data")
        data_dir.mkdir(exist_ok=True)
        (data_dir / "boss_result.json").write_text(
            json.dumps(all_jobs, ensure_ascii=False, indent=2), encoding="utf-8")
        mapped = [to_job_dict(j) for j in all_jobs]
        (data_dir / "boss_jobs.json").write_text(
            json.dumps(mapped, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已保存 boss_jobs.json ({len(mapped)} 条)", flush=True)
        for j in mapped[:5]:
            print(f"  {j['title'][:30]} | {j['company'][:14]} | {j['salary_desc']} | {j['city']}")


if __name__ == "__main__":
    main()
