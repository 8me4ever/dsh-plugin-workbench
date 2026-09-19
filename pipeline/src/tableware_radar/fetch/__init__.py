"""抓取层门面：导出 ``get_fetcher()`` 工厂与薄接口契约。

**下游只经此模块获取抓取器**，绝不 import 具体实现（``fixture`` / ``amazon_uk``），
从而把「抓取怎么实现」与「抓到之后怎么处理」彻底解耦（ARCHITECTURE §3.3）。
"""

from __future__ import annotations

from typing import Any

from .base import Fetcher, FetchReport, RawReview
from .fixture import FixtureFetcher

__all__ = [
    "Fetcher", "RawReview", "FetchReport", "FixtureFetcher", "get_fetcher",
    # 编排层（T04）—— 惰性导出，见下方 ``__getattr__``。
    "AmazonUkRun", "FetchRun", "AsinOutcome", "is_hard_stop", "write_raw_reviews",
]

# 支持的抓取器名（小写）。
_VALID_NAMES = ("amazon_uk", "fixture")

#: 惰性导出的编排层符号（避免顶层 import ``amazon_uk`` —— 它虽无 scrapling 顶层依赖，
#: 但延迟到真正使用时再引入，保持门面轻量、也守住"下游经门面取用"的约定）。
_LAZY_EXPORTS = frozenset(
    {"AmazonUkRun", "FetchRun", "AsinOutcome", "is_hard_stop", "write_raw_reviews"}
)


def __getattr__(name: str) -> Any:
    """PEP 562：按需从 ``.amazon_uk`` 导出编排层符号（``from .fetch import AmazonUkRun``）。"""
    if name in _LAZY_EXPORTS:
        from . import amazon_uk

        return getattr(amazon_uk, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_fetcher(name: str | None = None) -> Fetcher:
    """按名称返回抓取器实例。

    * ``"fixture"``    —— 离线确定性假数据（无网络，供开发/测试/下游联调）。
    * ``"amazon_uk"``  —— 真实抓取（Scrapling 纯 HTTP；惰性导入，无需预装也可导入本模块）。
    * ``None``         —— 回退到 ``config.FETCHER_NAME``（环境变量 ``TABLEWARE_FETCHER``）。

    ``amazon_uk`` 采用**惰性导入**：仅在真正选用时才 import Scrapling 实现，
    避免离线测试环境被迫安装抓取依赖。
    """
    from .. import config

    resolved = (name or config.FETCHER_NAME).strip().lower()
    if resolved == "fixture":
        return FixtureFetcher()
    if resolved == "amazon_uk":
        from .amazon_uk import ScraplingAmazonUkFetcher

        return ScraplingAmazonUkFetcher()
    raise ValueError(
        f"未知的 fetcher 名称: {resolved!r}（可选: {', '.join(_VALID_NAMES)}）"
    )
