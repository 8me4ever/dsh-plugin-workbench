"""抓取层**薄接口**契约（docs/ARCHITECTURE.md §3.3）。

设计目的：把「能不能抓到 / 怎么抓」与「抓到之后怎么处理」彻底解耦。
下游（``clean`` / ``stage_a`` / ``stage_c`` / ``aggregate``）**只依赖本模块的
``Fetcher`` Protocol 与 ``RawReview``/``FetchReport`` 数据结构**，**不得** import
任何具体 fetcher（``fixture`` / ``amazon_uk``）。探针结论落地后只替换
``fetch/amazon_uk.py``，其余文件零改动 —— 这正是薄接口隔离的价值。

``RawReview`` / ``FetchReport`` 的**唯一定义**在 ``..models``，此处 re-export 以让
本模块自身即为完整契约面（契约文档把这两个结构挂在本文件下）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import FetchReport, RawReview

__all__ = ["RawReview", "FetchReport", "Fetcher"]


@runtime_checkable
class Fetcher(Protocol):
    """抓取器协议。任何实现都必须满足：

    * ``version``：语义化版本字符串（写进 ``FetchReport.fetcher_version``）。
    * ``fetch_reviews(asin, limit)``：返回 ``(reviews, report)``。
      **串行、无翻页**；出现验证码/登录墙时把原因写入 ``report.error`` 并停止该 ASIN。
    """

    version: str

    def fetch_reviews(self, asin: str, limit: int) -> tuple[list[RawReview], FetchReport]:
        ...
