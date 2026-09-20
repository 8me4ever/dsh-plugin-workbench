"""第三轮探测:国内招聘平台公开接口 + 海外远程源 + GitHub 系聚合。"""
import asyncio

import httpx
from feedparser import parse

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


async def check(name: str, url: str, timeout: int = 12, is_json: bool = False, headers: dict | None = None):
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            r = await c.get(url, headers=headers or {"User-Agent": UA})
            if is_json:
                try:
                    data = r.json()
                    size = len(data) if isinstance(data, (list, dict)) else len(r.text)
                    print(f"[OK] {name}: status={r.status_code} json_size={size}")
                except Exception:  # noqa: BLE001
                    print(f"[HTML?] {name}: status={r.status_code} len={len(r.text)}")
            else:
                f = parse(r.content)
                n = len(f.entries)
                title = f.feed.get("title", "")[:40] if f.feed else ""
                print(f"[{'OK' if n > 0 else 'EMPTY'}] {name}: status={r.status_code} entries={n} feed={title}")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] {name}: {type(e).__name__} {str(e)[:70]}")


async def main():
    # 海外远程岗位 RSS(连通性测试)
    await check("remoteok python jobs rss", "https://remoteok.com/remote-python+jobs.rss")
    await check("weworkremotely rss", "https://weworkremotely.com/categories/remote-programming-jobs.rss")

    # 国内招聘平台连通性(能通即可,后续再做结构化解析)
    await check("智联首页", "https://www.zhaopin.com/", is_json=False)
    await check("智联搜索API(数据分析/北京)", "https://fe-api.zhaopin.com/c/i/sou?cityId=530&kw=%E6%95%B0%E6%8D%AE%E5%88%86%E6%9E%90", is_json=True)
    await check("猎聘首页", "https://www.liepin.com/")
    await check("拉勾首页", "https://www.lagou.com/")
    await check("BOSS直聘首页", "https://www.zhipin.com/")
    await check("前程无忧首页", "https://www.51job.com/")


if __name__ == "__main__":
    asyncio.run(main())
