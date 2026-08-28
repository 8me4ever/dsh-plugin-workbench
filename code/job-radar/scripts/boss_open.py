"""打开 Chromium 窗口,操作完全由用户手动完成。

用法:
  python scripts/boss_open.py                    # 打开百度首页(默认)
  python scripts/boss_open.py --url https://www.zhipin.com   # 打开指定页面
  python scripts/boss_open.py --minutes 60       # 最长停留 60 分钟

说明:
  - 使用 playwright 自带 Chromium + 独立 profile(data/.boss_profile),
    登录态会保存在该 profile,之后 boss.py check/fetch 直接复用。
  - 不做任何自动检测/自动关闭,窗口一直保留到你手动关掉或超时。
  - 登录完成后请告知,再运行 check/fetch。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boss import launch_context  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="打开 Chromium 窗口(手动操作)")
    ap.add_argument("--minutes", type=int, default=30, help="窗口最长停留分钟数")
    ap.add_argument("--url", default="https://www.baidu.com", help="起始页面(默认百度)")
    args = ap.parse_args()

    print(f"[open] 正在打开 Chromium 窗口(最长停留 {args.minutes} 分钟)...", flush=True)
    print(f"[open] 起始地址: {args.url}", flush=True)
    print("[open] 请在窗口里手动操作;完成后关闭窗口或 Ctrl+C 结束本脚本。", flush=True)

    with sync_playwright() as p:
        ctx = launch_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        print("[open] 窗口已打开,等待你手动操作...", flush=True)

        deadline = time.time() + args.minutes * 60
        try:
            while time.time() < deadline and ctx.pages:
                time.sleep(2)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                ctx.close()
            except Exception:  # noqa: BLE001
                pass
    print("[open] 窗口已关闭。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
