"""探索:招聘平台网页版 HTML 抓取 + GitHub 托管招聘 feed。"""
import json
import re

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def probe_html(name: str, url: str):
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=15, follow_redirects=True)
        text = r.text
        print(f"[{name}] status={r.status_code} html_len={len(text)}")
        # 找内嵌 JSON 或岗位关键词
        has_jobname = "jobName" in text or "岗位名称" in text or "positionName" in text
        print(f"    含岗位字段: {has_jobname}")
        # 找 title 标签
        m = re.search(r"<title>(.*?)</title>", text, re.S)
        print(f"    title: {m.group(1)[:60] if m else 'N/A'}")
        return text
    except Exception as e:  # noqa: BLE001
        print(f"[{name}] FAIL {type(e).__name__}: {str(e)[:70]}")
        return ""


def probe_feed(name: str, url: str):
    from feedparser import parse

    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=15, follow_redirects=True)
        f = parse(r.content)
        n = len(f.entries)
        title = f.feed.get("title", "")[:50] if f.feed else ""
        print(f"[{name}] status={r.status_code} entries={n} feed={title}")
        if f.entries:
            e = f.entries[0]
            print(f"    首条: {getattr(e, 'title', '')[:60]} | {getattr(e, 'link', '')[:60]}")
    except Exception as e:  # noqa: BLE001
        print(f"[{name}] FAIL {type(e).__name__}: {str(e)[:70]}")


probe_html("智联搜索页 sou.zhaopin.com", "https://sou.zhaopin.com/?jl=530&kw=python")
probe_html("猎聘搜索页", "https://www.liepin.com/zhaopin/?key=python")
probe_html("51job 搜索页", "https://we.51job.com/pc/search?jobArea=010000&keyword=python")
probe_html("拉勾搜索页", "https://www.lagou.com/wn/zhaopin?kd=python")

print("=" * 50)
# GitHub 系:GitHub Jobs 已关闭,试试 GitHub 上托管的招聘聚合 RSS
probe_feed("GitHub Trending RSS(每日)", "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml")
probe_feed("Hacker News 招聘(hnrss)", "https://hnrss.org/jobs")
