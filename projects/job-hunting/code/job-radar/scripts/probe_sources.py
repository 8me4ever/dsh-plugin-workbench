"""探测可用招聘聚合源:测试 RSSHub 实例与招聘路由。"""
import asyncio
import sys

import httpx
from feedparser import parse


async def check(name: str, url: str, timeout: int = 12):
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            r = await c.get(url)
            f = parse(r.content)
            n = len(f.entries)
            title = f.feed.get("title", "")[:40] if f.feed else ""
            print(f"[{'OK' if n > 0 else 'EMPTY'}] {name}: status={r.status_code} entries={n} feed={title}")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] {name}: {type(e).__name__} {str(e)[:70]}")


async def main():
    candidates = [
        ("RSSHub 官方实例", "https://rsshub.app"),
        ("RSSHub 路由:远程工作(remote-work/jobs)", "https://rsshub.app/remote-work/jobs"),
        ("RSSHub 路由:电鸭社区(eleduck/jobs)", "https://rsshub.app/eleduck/jobs"),
        ("RSSHub 路由:Ruby China 招聘", "https://rsshub.app/ruby-china/jobs"),
        ("RSSHub 路由:V2EX 酷工作", "https://rsshub.app/v2ex/tab/jobs"),
        ("RSSHub 路由:拉勾(lagou/jobs/数据分析/北京)", "https://rsshub.app/lagou/jobs/数据分析/北京"),
        ("RSSHub 路由:智联(zhaopin/北京/数据分析)", "https://rsshub.app/zhaopin/北京/数据分析"),
        ("RSSHub 路由:牛客(nowcoder/jobcenter)", "https://rsshub.app/nowcoder/jobcenter"),
    ]
    for name, url in candidates:
        await check(name, url)


if __name__ == "__main__":
    asyncio.run(main())
