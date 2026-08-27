"""BOSS直聘 采集器(登录与抓取解耦)。

设计:
  - 登录(login)与抓取(fetch)完全分开。登录是你本人手动扫码的一次性动作,
    登录态(cookie)保存到 data/.boss_profile(已 gitignore)。
  - 抓取前先「检查登录态」,已登录才继续,未登录则直接提示,绝不碰登录页。

用法:
  python scripts/boss.py check    # 只检查是否已登录
  python scripts/boss.py login    # 打开浏览器窗口,等你手动扫码登录(保存登录态)
  python scripts/boss.py fetch    # 检查登录态 → 抓取「数据分析·北京」岗位

网络说明:
  本机 Clash 的 fake-ip DNS 会把 zhipin.com 错解析到百度,故用 direct + 真实 IP 映射绕过;
  同时隐藏 navigator.webdriver,避免触发 BOSS 反爬安全校验(否则登录页会不停刷新)。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROFILE_DIR = DATA / ".boss_profile"
QR_PATH = DATA / "boss_qr.png"
HTML_PATH = DATA / "boss_search.html"
SHOT_PATH = DATA / "boss_search.png"
RESULT_PATH = DATA / "boss_result.json"

SEARCH_URL = (
    "https://www.zhipin.com/web/geek/job"
    "?query=%E6%95%B0%E6%8D%AE%E5%88%86%E6%9E%90&city=101010100"  # 数据分析·北京
)

# zhipin 各子域名真实 IP(DoH 查询,绕过 Clash fake-ip 错配)
_ZHIPIN_IP = {
    "www.zhipin.com": "211.159.143.184",
    "api.zhipin.com": "49.233.246.183",
    "static.zhipin.com": "101.73.101.60",
    "img.bosszhipin.com": "119.249.48.19",
    "s.zhipin.com": "39.96.33.114",
}
_ZHIPIN_FALLBACK = {
    "*.zhipin.com": "211.159.143.184",
    "*.bosszhipin.com": "119.249.48.19",
}

# 岗位卡片 / 登录页标志选择器
CARD_SELECTORS = [
    ".job-card-wrapper", ".job-card-box", ".job-list-box li", ".job-list li",
]
LOGIN_SELECTORS = [
    ".login-entry-page", ".login-register-content", ".ewm-switch", ".login-phone-wrapper",
]


def log(msg: str) -> None:
    print(f"[BOSS] {msg}", flush=True)


def build_host_resolver_rules() -> str:
    rules = [f"MAP {h} {ip}" for h, ip in _ZHIPIN_IP.items()]
    rules += [f"MAP {h} {ip}" for h, ip in _ZHIPIN_FALLBACK.items()]
    return ", ".join(rules)


def launch_context(p, channel: str = "msedge"):
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        channel=channel,
        args=[
            "--proxy-server=direct://",
            f"--host-resolver-rules={build_host_resolver_rules()}",
            "--disable-blink-features=AutomationControlled",
        ],
        viewport={"width": 1280, "height": 900},
    )
    ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    return ctx


def has_cards(page) -> bool:
    for sel in CARD_SELECTORS:
        if page.locator(sel).count() > 0:
            return True
    return False


def has_login(page) -> bool:
    for sel in LOGIN_SELECTORS:
        if page.locator(sel).count() > 0:
            return True
    return "/web/user/" in page.url or "登录" in page.title()


def wait_any(page, selectors: list[str], timeout_s: int = 45) -> str | None:
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=timeout_s * 1000)
            return sel
        except Exception:  # noqa: BLE001
            continue
    return None


def check_login(page) -> bool:
    """导航到搜索页,判断是否已登录。返回 True=已登录。"""
    page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
    wait_any(page, CARD_SELECTORS + LOGIN_SELECTORS, timeout_s=45)
    page.wait_for_timeout(2000)
    if has_cards(page):
        return True
    if has_login(page):
        return False
    return False


def extract_cards(page) -> list[dict]:
    items = page.query_selector_all(
        ".job-card-wrapper, .job-card-box, .job-list-box li, .job-list li"
    )
    cards = []
    for it in items:
        def text(sel):
            el = it.query_selector(sel)
            return el.inner_text().strip() if el else ""

        card = {
            "title": text(".job-name") or text(".job-title") or text(".job-info .job-name"),
            "salary": text(".salary") or text(".job-salary"),
            "company": text(".company-name") or text(".boss-name") or text(".company-text"),
            "area": text(".job-area") or text(".job-location"),
            "tags": text(".tag-list") or text(".job-info"),
            "link": "",
        }
        a = it.query_selector("a[href*='/job_detail/'], a[href*='job_detail']")
        if a:
            card["link"] = a.get_attribute("href") or ""
        cards.append(card)
    return cards


def cmd_check() -> int:
    with sync_playwright() as p:
        ctx = launch_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        ok = check_login(page)
        if ok:
            log("✅ 已登录 BOSS直聘")
        else:
            log("❌ 未登录。请运行: python scripts/boss.py login")
        ctx.close()
    return 0 if ok else 1


def cmd_login(timeout_s: int = 360) -> int:
    with sync_playwright() as p:
        ctx = launch_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        wait_any(page, CARD_SELECTORS + LOGIN_SELECTORS, timeout_s=45)
        page.wait_for_timeout(2000)

        if has_cards(page):
            log("✅ 已处于登录状态,无需再次登录")
            ctx.close()
            return 0

        page.screenshot(path=str(QR_PATH))
        log(f"登录页截图已保存: {QR_PATH}")
        log(">>> 请在 Edge 窗口里手动扫码登录(用 BOSS直聘 APP 扫二维码,或在页面里自己选择登录方式) <<<")
        log(f"等待登录完成(最长 {timeout_s} 秒)...")

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            time.sleep(4)
            if has_cards(page):
                log("✅ 检测到岗位列表,登录成功,登录态已保存")
                ctx.close()
                return 0
            if not has_login(page):
                log("✅ 登录页已消失,疑似登录成功,登录态已保存")
                ctx.close()
                return 0
        log("❌ 登录超时,未检测到登录成功")
        ctx.close()
        return 2


def cmd_fetch() -> int:
    with sync_playwright() as p:
        ctx = launch_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        log("检查登录态...")
        if not check_login(page):
            log("❌ 未登录,中止抓取。请先运行: python scripts/boss.py login")
            ctx.close()
            return 1

        log("已登录,开始抓取...")
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        wait_any(page, CARD_SELECTORS, timeout_s=30)
        page.wait_for_timeout(4000)
        for _ in range(4):
            page.mouse.wheel(0, 3000)
            time.sleep(1.5)
        page.wait_for_timeout(2000)

        html = page.content()
        HTML_PATH.write_text(html, encoding="utf-8")
        log(f"已保存页面 HTML: {HTML_PATH}")
        page.screenshot(path=str(SHOT_PATH), full_page=True)
        log(f"已保存整页截图: {SHOT_PATH}")

        cards = extract_cards(page)
        log(f"提取到岗位卡片: {len(cards)} 条")
        RESULT_PATH.write_text(
            json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"已保存提取结果: {RESULT_PATH}")
        if cards:
            log("前 5 条示例:")
            for c in cards[:5]:
                log(f"  {c['title']} | {c['salary']} | {c['company']} | {c['area']}")

        ctx.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="BOSS直聘 采集器")
    ap.add_argument("cmd", choices=["check", "login", "fetch"])
    ap.add_argument("--timeout", type=int, default=360, help="login 等待扫码的秒数")
    args = ap.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)
    if args.cmd == "check":
        return cmd_check()
    if args.cmd == "login":
        return cmd_login(args.timeout)
    return cmd_fetch()


if __name__ == "__main__":
    sys.exit(main())
