"""第二轮探测:公共 RSSHub 镜像 + 备选招聘源。"""
import asyncio

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
    # 公共 RSSHub 镜像(2025 年常见可用实例)
    mirrors = [
        "https://rsshub.rssforever.com",
        "https://rsshub.ktachibana.party",
        "https://rsshub.woodland.cafe",
        "https://hub.slarker.me",
        "https://rsshub.pseudoyu.com",
    ]
    # 各镜像测同一条招聘路由:远程工作
    route = "/remote-work/jobs"
    for m in mirrors:
        await check(f"镜像 {m}", m + route)

    # 不依赖 RSSHub 的备选源
    others = [
        ("远程工作官网 RSS(we work remotely)", "https://weworkremotely.com/categories/remote-programming-jobs.rss"),
        ("GitHub Trending(近实时)", "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml"),
        ("V2EX 最新(API 版)", "https://www.v2ex.com/api/topics/show.json?node_name=jobs"),
    ]
    for name, url in others:
        await check(name, url)


if __name__ == "__main__":
    asyncio.run(main())
