"""BOSS直聘 采集器(API 通道)。

核心思路(2026-08-28 重写):
  - BOSS 页面自动化访问会被反爬拦截(about:blank),但登录态 cookie 有效;
  - 改用官方搜索 API(wapi/zpgeek/search/joblist.json),带完整浏览器请求头
    (UA/Referer/Origin/Sec-Fetch)即可绕过环境风控,稳定拿到结构化 JSON。
  - 登录(login)仍由用户手动扫码一次性完成,登录态保存在 data/.boss_profile。

用法:
  python scripts/boss.py check     # 用 API 探测登录态是否有效(无需打开浏览器页面)
  python scripts/boss.py fetch     # 抓取「数据分析·北京」岗位 → 入库打分(需已登录)
  python scripts/boss.py fetch --query python --city 101010100 --pages 2
  python scripts/boss.py login     # (旧)打开浏览器窗口手动扫码,一般用 boss_open.py 代替

需要先运行一次: python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROFILE_DIR = DATA / ".boss_profile"

# 搜索 API 与页面 Referer
SEARCH_API = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
SEARCH_PAGE = "https://www.zhipin.com/web/geek/job"

# 城市:101010100=北京,101280600=深圳
CITY_BEIJING = "101010100"
CITY_SHENZHEN = "101280600"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

# 抓取任务:默认「数据分析·北京」(可在 fetch 参数覆盖)
DEFAULT_TASK = {"query": "数据分析", "city": CITY_BEIJING}


def log(msg: str) -> None:
    print(f"[BOSS] {msg}", flush=True)


def launch_context(p, channel: str = ""):
    """打开窗口模式浏览器(供 boss_open.py 手动登录/刷新会话使用)。

    默认用 playwright 自带 Chromium + 独立 profile;带反检测初始化脚本。
    """
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        channel=channel or None,
        args=[
            "--proxy-server=direct://",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        viewport={"width": 1280, "height": 900},
    )
    ctx.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        window.chrome = window.chrome || {runtime: {}};
        """
    )
    return ctx


def api_headers(query: str, city: str) -> dict:
    ref = f"{SEARCH_PAGE}?query={quote(query)}&city={city}"
    return {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": ref,
        "Origin": "https://www.zhipin.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


def fetch_jobs_page(
    ctx, query: str, city: str, page: int, page_size: int = 30,
    retries: int = 3,
) -> tuple[int, list[dict]]:
    """请求一页岗位。返回 (code, jobList)。

    风控说明:BOSS 对高频请求限流(code=37 环境异常)。连续请求间固定间隔,
    失败时指数退避重试;多次失败说明被标记,需冷却或重新登录。
    """
    req = ctx.request
    params = {
        "scene": "1", "query": query, "city": city,
        "page": str(page), "pageSize": str(page_size),
    }
    last_code = -1
    for attempt in range(1, retries + 1):
        if attempt > 1:
            wait = min(30, 5 * (2 ** (attempt - 1)))  # 5s, 10s, 20s 退避
            log(f"重试 {attempt}/{retries}(等待 {wait}s)...")
            time.sleep(wait)
        try:
            r = req.get(SEARCH_API, params=params, headers=api_headers(query, city), timeout=30000)
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            log(f"请求异常: {str(exc)[:100]}")
            last_code = -1
            continue
        last_code = data.get("code")
        if last_code == 0:
            zp = data.get("zpData", {}) or {}
            return 0, zp.get("jobList", [])
        log(f"code={last_code} message={data.get('message')}")
        if last_code != 37:
            break  # 非风控错误,不重试
    return last_code, []


def check_login(ctx) -> bool:
    """用 API 探测登录态:code=0 且有数据 → 已登录;code=37 → 环境异常/未登录。"""
    code, jobs = fetch_jobs_page(ctx, "数据分析", CITY_BEIJING, 1, 5)
    if code == 0:
        return True
    if code == 37:
        log("API 返回「环境存在异常」——可能是未登录或风控")
    return False


def to_job_dict(j: dict) -> dict:
    """把 BOSS API 岗位字段映射为 job-radar 通用字典。"""
    return {
        "title": j.get("jobName", ""),
        "company": j.get("brandName", ""),
        "city": j.get("cityName", ""),
        "salary_desc": j.get("salaryDesc", ""),
        "experience": j.get("jobExperience", ""),
        "education": j.get("jobDegree", ""),
        "skills": j.get("skills", []),
        "welfare": j.get("welfareList", []),
        "stage": j.get("brandStageName", ""),
        "scale": j.get("brandScaleName", ""),
        "industry": j.get("brandIndustry", ""),
        "district": j.get("areaDistrict", ""),
        "url": f"https://www.zhipin.com/job_detail/{j.get('encryptJobId')}.html",
    }


def cmd_check() -> int:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=True,
        )
        try:
            if check_login(ctx):
                log("✅ 登录态有效,API 可正常拉取岗位")
                return 0
            log("❌ 未登录或环境异常。请先运行: python scripts/boss_open.py 手动扫码登录")
            return 1
        finally:
            ctx.close()


def cmd_fetch(args: argparse.Namespace) -> int:
    query = args.query or DEFAULT_TASK["query"]
    city = args.city or DEFAULT_TASK["city"]
    pages = args.pages or 1

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=True,
        )
        try:
            if not check_login(ctx):
                log("❌ 未登录,中止抓取。请先运行 boss_open.py 手动登录")
                return 1
            all_jobs: list[dict] = []
            for pg in range(1, pages + 1):
                code, jobs = fetch_jobs_page(ctx, query, city, pg)
                if code != 0:
                    log(f"第 {pg} 页失败 code={code},停止抓取")
                    break
                all_jobs.extend(jobs)
                log(f"第 {pg} 页: {len(jobs)} 条")
                time.sleep(3.0)  # 页间温和限速,避免触发风控
            log(f"共获取 {len(all_jobs)} 条岗位")
        finally:
            ctx.close()

    # 落盘原始结果 + 映射为标准字段
    DATA.mkdir(parents=True, exist_ok=True)
    raw_path = DATA / "boss_result.json"
    raw_path.write_text(
        json.dumps(all_jobs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    mapped = [to_job_dict(j) for j in all_jobs]
    mapped_path = DATA / "boss_jobs.json"
    mapped_path.write_text(
        json.dumps(mapped, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"原始数据: {raw_path} ({len(all_jobs)} 条)")
    log(f"标准字段: {mapped_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="BOSS直聘 采集器(API 通道)")
    ap.add_argument("cmd", choices=["check", "fetch", "login"])
    ap.add_argument("--query", default=None, help="搜索关键词(默认:数据分析)")
    ap.add_argument("--city", default=None, help="城市代码(默认北京 101010100)")
    ap.add_argument("--pages", type=int, default=1, help="抓取页数(默认 1)")
    args = ap.parse_args()

    if args.cmd == "check":
        return cmd_check()
    if args.cmd == "fetch":
        return cmd_fetch(args)
    # login 旧命令提示用 boss_open.py
    print("[BOSS] 请使用 scripts/boss_open.py 打开浏览器窗口手动扫码登录")
    return 1


if __name__ == "__main__":
    sys.exit(main())
