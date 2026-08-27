"""采集器:从聚合源(RSSHub 等)抓取岗位信息。

V1 只接 RSS/Atom 聚合源,合规低风险。数据源在 config/sources.yaml 配置。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import feedparser
import httpx
import yaml

from .parser import ParsedJD

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(15.0)


@dataclass
class Source:
    """一个聚合订阅源。"""

    name: str
    url: str
    enabled: bool = True
    company_hint: str = ""  # 可选:源固定的公司名
    enrich_detail: bool = False  # 摘要过短时是否抓详情页补充正文

    @classmethod
    def from_dict(cls, d: dict) -> "Source":
        return cls(
            name=d.get("name", ""),
            url=d.get("url", ""),
            enabled=d.get("enabled", True),
            company_hint=d.get("company", ""),
            enrich_detail=d.get("enrich_detail", False),
        )


def load_sources(path: str | Path | None = None) -> list[Source]:
    """从 config/sources.yaml 读取订阅源。文件不存在时返回空列表。"""
    if path is None:
        path = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"
    p = Path(path)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return [Source.from_dict(d) for d in data.get("sources", [])]


def fetch_feed(
    url: str,
    client: httpx.Client | None = None,
) -> list[dict]:
    """抓取一个 RSS/Atom 源,返回条目列表。

    每条: {title, link, summary, published, author}
    """
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True)
    try:
        resp = client.get(url)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        entries = []
        for e in feed.entries:
            entries.append(
                {
                    "title": getattr(e, "title", ""),
                    "link": getattr(e, "link", ""),
                    "summary": getattr(e, "summary", ""),
                    "published": getattr(e, "published", ""),
                    "author": getattr(e, "author", ""),
                }
            )
        return entries
    except Exception as exc:  # noqa: BLE001
        logger.warning("抓取失败 %s: %s", url, exc)
        return []
    finally:
        if own_client:
            client.close()


def fetch_detail(url: str, client: httpx.Client | None = None) -> str:
    """抓取岗位详情页正文(用于摘要稀疏的源,如 HN Jobs)。

    仅抓取明显可用的 URL(https),失败时返回空串,不影响主流程。
    """
    if not url or not url.startswith("http"):
        return ""
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True)
    try:
        resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (job-radar/0.1)"})
        if resp.status_code != 200:
            return ""
        text = resp.text
        # 轻量 HTML → 文本:去脚本/样式/标签
        import re

        text = re.sub(r"<script[\s\S]*?</script>", " ", text)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:4000]  # 截断,控制体积
    except Exception as exc:  # noqa: BLE001
        logger.debug("详情页抓取失败 %s: %s", url, exc)
        return ""
    finally:
        if own_client:
            client.close()


def collect(
    sources: list[Source],
    parse_skills: list[str],
    on_job: Callable[[ParsedJD, str], None] | None = None,
) -> int:
    """抓取所有启用的源,逐条解析并回调。

    Args:
        sources: 订阅源列表。
        parse_skills: 技能关键词(用于解析器命中技能)。
        on_job: 每条解析后的回调(通常是 storage.upsert_job)。
    Returns:
        成功解析的岗位数。
    """
    count = 0
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        for src in sources:
            if not src.enabled:
                continue
            logger.info("抓取源: %s (%s)", src.name, src.url)
            for entry in fetch_feed(src.url, client):
                parsed = parse_entry(entry, src, parse_skills, client)
                if on_job:
                    on_job(parsed, src.name)
                count += 1
    return count


def parse_entry(
    entry: dict,
    src: Source,
    parse_skills: list[str],
    client: httpx.Client | None = None,
) -> ParsedJD:
    """把 feed 条目转为 ParsedJD。

    摘要过短(稀疏源,如 HN Jobs)时,自动抓取详情页(entry.link)补充正文。
    """
    from .parser import parse_jd

    title = entry.get("title", "")
    summary = entry.get("summary", "") or ""
    author = entry.get("author", "") or ""
    # summary 可能带 HTML,做轻量清洗
    import re

    summary = re.sub(r"<[^>]+>", " ", summary)
    summary = re.sub(r"\s+", " ", summary).strip()

    text = f"{title}\n{summary}\n{author}"
    # 源配置了 enrich_detail 时,无条件抓详情页补正文(HN 等链接型源,摘要只有 URL 占位)
    if src.enrich_detail and entry.get("link"):
        detail = fetch_detail(entry["link"], client)
        if detail:
            text = f"{title}\n{detail}"
            # 公司名从详情页标题提取(如 "Founding Product Engineer at Proliferate")
            m = re.search(r"\bat\s+([A-Za-z0-9&.\- ]{2,30})\s*\|?", detail[:200])
            if m and not src.company_hint:
                author = m.group(1).strip()

    return parse_jd(
        text,
        plus_skills=parse_skills,
        title=title,
        company=src.company_hint or author,
        url=entry.get("link", ""),
    )
