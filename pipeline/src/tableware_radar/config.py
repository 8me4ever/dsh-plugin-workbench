"""全部可调参数与路径常量 —— 管道的**唯一配置入口**。

设计硬约束（见 docs/ARCHITECTURE.md §5 T01 验收 / §7 共享知识）：

* **ASIN 清单与每 ASIN 条数必须是配置项**，下游任何模块都不得硬编码。
  优先级：环境变量 ``TABLEWARE_ASINS`` > ``config/asins.txt`` > 内置默认。
* **``rankable`` 三阈值**（``HITS_MIN`` / ``ASIN_RATIO`` / ``ASIN_FLOOR``）**必须可配置**：
  数据规模预期从 8–10 个 ASIN 扩到 30 个（R7），比例式阈值使得扩容无需改代码。
* **24 个月时间窗**为单一常量，抓取层与清洗层共用（U6）。
* **两个闸门阈值**（``other`` 占比 / 失败率）与 **两个分母口径**在此集中声明；
  ⚠️ 两者口径不同、**禁止统一**（见 §7）。
* 所有可调值均可被同名环境变量覆盖，方便 CI / 开发机 / 生产一致运行。
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

from dateutil.relativedelta import relativedelta

__all__ = [
    "PACKAGE_DIR", "PIPELINE_DIR", "SRC_DIR", "REPO_ROOT",
    "CONFIG_DIR", "DATA_DIR", "DOCS_DIR",
    "LOGS_DIR", "RAW_DIR", "CLEAN_DIR", "TOPICS_DIR", "LABELED_DIR",
    "ANALYSIS_PATH", "DIMENSIONS_PATH", "DIMENSIONS_EXAMPLE_PATH",
    "ASINS_FILE", "FETCH_REPORT_PATH", "ALL_DATA_DIRS", "ensure_data_dirs",
    "MARKETPLACE", "BASE_URL", "LOCALE", "TIMEZONE",
    "DEFAULT_ASINS", "load_asins", "ASINS",
    "PLATFORM_CAP_PER_ASIN", "TARGET_REVIEWS_PER_ASIN", "MIN_REVIEWS_PER_ASIN",
    "MIN_USABLE_CHARS", "FETCH_REQUEST_LIMIT", "TIME_WINDOW_MONTHS",
    "RANKABLE_HITS_MIN", "RANKABLE_ASIN_RATIO", "RANKABLE_ASIN_FLOOR",
    "rankable_asin_threshold", "MATRIX_TOP_ASINS", "MATRIX_TOP_ASINS_MIN",
    "MATRIX_TOP_ASINS_MAX", "RANKABLE_DIM_MIN",
    "FETCHER_NAME", "DIMENSION_SET_VERSION", "PROMPT_VERSION", "FETCHER_VERSION",
    "LLM_PROFILE", "LLM_BATCH_SIZE", "LLM_BATCH_MIN", "LLM_BATCH_MAX",
    "LLM_TASK_CHAR_LIMIT", "LLM_TIMEOUT_S", "LLM_WARMUP_TIMEOUT_S", "LLM_MAX_RETRIES",
    "OTHER_GATE_MAX", "FAILURE_GATE_MAX", "PILOT_SIZE", "STAGE_A_SAMPLE_PER_ASIN",
    "FETCH_PAGE_TIMEOUT_S", "FETCH_MIN_DELAY_S", "FETCH_MAX_DELAY_S",
    "FETCH_MAX_ATTEMPTS", "FETCH_BACKOFF_FACTOR", "RESERVE_ASINS",
    "now_iso", "today_utc", "within_window",
]


# --------------------------------------------------------------------------- #
# 路径常量
# --------------------------------------------------------------------------- #

PACKAGE_DIR = Path(__file__).resolve().parent          # .../pipeline/src/tableware_radar
SRC_DIR = PACKAGE_DIR.parent                           # .../pipeline/src
PIPELINE_DIR = SRC_DIR.parent                          # .../pipeline
REPO_ROOT = PIPELINE_DIR.parent                        # .../dsh-tableware-radar

CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"

LOGS_DIR = DATA_DIR / "logs"
RAW_DIR = DATA_DIR / "raw"
CLEAN_DIR = DATA_DIR / "clean"
TOPICS_DIR = DATA_DIR / "topics"
LABELED_DIR = DATA_DIR / "labeled"

ANALYSIS_PATH = DATA_DIR / "analysis.json"
DIMENSIONS_PATH = CONFIG_DIR / "dimensions.yaml"
DIMENSIONS_EXAMPLE_PATH = CONFIG_DIR / "dimensions.example.yaml"
ASINS_FILE = CONFIG_DIR / "asins.txt"
FETCH_REPORT_PATH = RAW_DIR / "fetch_report.json"

ALL_DATA_DIRS = (DATA_DIR, LOGS_DIR, RAW_DIR, CLEAN_DIR, TOPICS_DIR, LABELED_DIR)


def ensure_data_dirs() -> None:
    """幂等地创建全部数据目录（管道启动时调用一次）。"""
    for directory in ALL_DATA_DIRS:
        directory.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# 环境变量读取helper（带类型转换与静默回退）
# --------------------------------------------------------------------------- #

_T = TypeVar("_T")


def _env_raw(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env(name: str, default: _T, cast: Callable[[str], _T]) -> _T:
    raw = _env_raw(name)
    if raw is None:
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return default


def _env_str(name: str, default: str) -> str:
    return _env(name, default, str)


def _env_int(name: str, default: int) -> int:
    return _env(name, default, int)


def _env_float(name: str, default: float) -> float:
    return _env(name, default, float)


# --------------------------------------------------------------------------- #
# 时间工具（全管道统一 UTC / ISO 8601）
# --------------------------------------------------------------------------- #

def now_iso() -> str:
    """当前 UTC 时间，ISO 8601（秒级），如 ``2026-09-19T08:30:00Z``。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_utc() -> str:
    """当前 UTC 日期 ``YYYY-MM-DD``（评论日期无时区语义）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def within_window(
    date_str: str,
    *,
    now: datetime | None = None,
    months: int | None = None,
) -> bool:
    """评论日期是否落在最近 ``months`` 个月内（**U6 时间窗的唯一判据**）。

    抓取层（T04）据此**不落盘**窗口外评论；清洗层（T03）据此**再兜底**丢弃 ——
    两处共用本函数，避免同一口径写两遍写歪。

    日期缺失（``""``）或无法解析 → **返回 True**（宁可保留也不误删，见 §7）。
    """
    if not date_str:
        return True
    try:
        review_dt = datetime.strptime(str(date_str), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True
    window = TIME_WINDOW_MONTHS if months is None else months
    cutoff = (now or datetime.now(timezone.utc)) - relativedelta(months=window)
    return review_dt >= cutoff


# --------------------------------------------------------------------------- #
# 目标市场
# --------------------------------------------------------------------------- #

MARKETPLACE = _env_str("TABLEWARE_MARKETPLACE", "amazon.co.uk")
BASE_URL = _env_str("TABLEWARE_BASE_URL", "https://www.amazon.co.uk")
LOCALE = _env_str("TABLEWARE_LOCALE", "en-GB")
TIMEZONE = _env_str("TABLEWARE_TIMEZONE", "Europe/London")


# --------------------------------------------------------------------------- #
# ASIN 清单（★ 关键：配置项，绝不硬编码到下游）
# --------------------------------------------------------------------------- #

# 内置兜底仅含**探针实测确认真实在售**的 ASIN（B0157FD9MS，
# Amazon Basics 6-Piece White Dinner Plate Set —— 见 probe/REPORT.md §2）。
# 正式运行请通过 config/asins.txt 或环境变量提供 8–10 个自选 ASIN（U4）。
DEFAULT_ASINS: tuple[str, ...] = ("B0157FD9MS",)


def _normalize_asin(value: str) -> str:
    return value.strip().strip(",").upper()


def load_asins() -> tuple[str, ...]:
    """按优先级解析 ASIN 清单：环境变量 → ``config/asins.txt`` → 内置默认。

    ``config/asins.txt`` 支持 ``#`` 行内注释与空行。解析结果去重且保持顺序。
    """
    env = _env_raw("TABLEWARE_ASINS")
    if env:
        raw_items = env.split(",")
    elif ASINS_FILE.exists():
        raw_items = []
        for line in ASINS_FILE.read_text(encoding="utf-8").splitlines():
            raw_items.append(line.split("#", 1)[0])
    else:
        raw_items = list(DEFAULT_ASINS)

    seen: dict[str, None] = {}
    for item in raw_items:
        asin = _normalize_asin(item)
        if asin:
            seen.setdefault(asin, None)
    if not seen:
        return DEFAULT_ASINS
    return tuple(seen.keys())


# 模块级快照：多数场景直接用 ``config.ASINS``；需重新读取时调用 ``load_asins()``。
ASINS: tuple[str, ...] = load_asins()


# --------------------------------------------------------------------------- #
# 抓取条数与时间窗
# --------------------------------------------------------------------------- #

# 单 ASIN 的平台硬上限（探针实测首屏 "Top reviews" 挂件上限 = 13）。
PLATFORM_CAP_PER_ASIN = _env_int("TABLEWARE_PLATFORM_CAP", 13)
# 每 ASIN 目标条数（首屏口径；翻页需登录，不做）。
TARGET_REVIEWS_PER_ASIN = _env_int("TABLEWARE_TARGET_PER_ASIN", PLATFORM_CAP_PER_ASIN)
# 单 ASIN 判定「成功」的最低条数。
MIN_REVIEWS_PER_ASIN = _env_int("TABLEWARE_MIN_PER_ASIN", 10)
# 清洗层：判定单条评论「可用」的最短正文字符数（过短视为噪声，不计入聚合分母）。
MIN_USABLE_CHARS = _env_int("TABLEWARE_MIN_USABLE_CHARS", 20)
# 传给 fetch_reviews(asin, limit) 的请求上限（大于平台上限，由抓取层自然截断）。
FETCH_REQUEST_LIMIT = _env_int("TABLEWARE_FETCH_LIMIT", 100)

# ★ U6：评论时间窗（月）。抓取层按此截断，且窗口外评论不落盘。
TIME_WINDOW_MONTHS = _env_int("TABLEWARE_TIME_WINDOW_MONTHS", 24)


# --------------------------------------------------------------------------- #
# ★ rankable 三阈值（R2/R7）—— 必须可配置，禁硬编码
# --------------------------------------------------------------------------- #

RANKABLE_HITS_MIN = _env_int("TABLEWARE_HITS_MIN", 3)
RANKABLE_ASIN_RATIO = _env_float("TABLEWARE_ASIN_RATIO", 0.3)
RANKABLE_ASIN_FLOOR = _env_int("TABLEWARE_ASIN_FLOOR", 3)

# ③ 对比矩阵默认列数（5–8），及允许范围。
MATRIX_TOP_ASINS = _env_int("TABLEWARE_MATRIX_TOP_ASINS", 5)
MATRIX_TOP_ASINS_MIN = 5
MATRIX_TOP_ASINS_MAX = 8

# 降级安全阀：rankable 维度少于该数时提示数据不足（不改口径，见 R7）。
RANKABLE_DIM_MIN = _env_int("TABLEWARE_RANKABLE_DIM_MIN", 3)


def rankable_asin_threshold(asins_with_data: int) -> int:
    """``asin_count`` 达标线 = ``max(ASIN_FLOOR, ceil(ASIN_RATIO × asins_with_data))``。

    比例项保证数据规模扩到 30 个 ASIN 时无需改代码（R7）。
    """
    if asins_with_data <= 0:
        return RANKABLE_ASIN_FLOOR
    return max(RANKABLE_ASIN_FLOOR, math.ceil(RANKABLE_ASIN_RATIO * asins_with_data))


# --------------------------------------------------------------------------- #
# 版本号与抓取器选择
# --------------------------------------------------------------------------- #

FETCHER_NAME = _env_str("TABLEWARE_FETCHER", "amazon_uk")   # amazon_uk | fixture
DIMENSION_SET_VERSION = _env_str("TABLEWARE_DIMENSIONS_VERSION", "dims-v1")
PROMPT_VERSION = _env_str("TABLEWARE_PROMPT_VERSION", "prompt-0.3")
FETCHER_VERSION = "0.1.0"


# --------------------------------------------------------------------------- #
# LLM（dsh --profile headless 子进程）
# --------------------------------------------------------------------------- #

LLM_PROFILE = _env_str("TABLEWARE_LLM_PROFILE", "headless")
LLM_BATCH_SIZE = _env_int("TABLEWARE_LLM_BATCH", 20)
LLM_BATCH_MIN = 15
LLM_BATCH_MAX = 20
# 单批任务文本字符上限（规避 Windows 32767 命令行长度上限，见 §7）。
LLM_TASK_CHAR_LIMIT = _env_int("TABLEWARE_LLM_CHAR_LIMIT", 8000)
LLM_TIMEOUT_S = _env_int("TABLEWARE_LLM_TIMEOUT", 60)             # 暖机后单次
LLM_WARMUP_TIMEOUT_S = _env_int("TABLEWARE_LLM_WARMUP_TIMEOUT", 360)  # 首次冷启动 ~212s
LLM_MAX_RETRIES = _env_int("TABLEWARE_LLM_RETRIES", 2)


# --------------------------------------------------------------------------- #
# 阶段闸门与抽样
# --------------------------------------------------------------------------- #

# ★ 闸门①：other 占比 > OTHER_GATE_MAX —— 分母**只算 ok=true**。
OTHER_GATE_MAX = _env_float("TABLEWARE_OTHER_GATE", 0.15)
# ★ 闸门②：失败率 > FAILURE_GATE_MAX —— 分母为**已处理条数**。
# ⚠️ 与闸门①口径不同，禁止统一（见 §7）。
FAILURE_GATE_MAX = _env_float("TABLEWARE_FAILURE_GATE", 0.10)
# 闸门①在 pilot 批量上先行探路。
PILOT_SIZE = _env_int("TABLEWARE_PILOT_SIZE", 20)
# 阶段 A 每 ASIN 抽样条数（R6）。
STAGE_A_SAMPLE_PER_ASIN = _env_int("TABLEWARE_STAGE_A_SAMPLE", 10)


# --------------------------------------------------------------------------- #
# 抓取限速与超时
# --------------------------------------------------------------------------- #

FETCH_PAGE_TIMEOUT_S = _env_int("TABLEWARE_FETCH_TIMEOUT", 30)
FETCH_MIN_DELAY_S = _env_float("TABLEWARE_FETCH_MIN_DELAY", 3.0)
FETCH_MAX_DELAY_S = _env_float("TABLEWARE_FETCH_MAX_DELAY", 8.0)
# 单 ASIN 的**请求级**最大尝试次数（重试上限，非"换 ASIN"次数）。
FETCH_MAX_ATTEMPTS = _env_int("TABLEWARE_FETCH_ATTEMPTS", 3)
# 退避倍率：第 n 次重试的等待上界 = min(MAX_DELAY, MIN_DELAY × FACTOR^(n-2))。
FETCH_BACKOFF_FACTOR = _env_float("TABLEWARE_FETCH_BACKOFF", 2.0)


# --------------------------------------------------------------------------- #
# 备选 ASIN 池（T04 换选；方案 B：N 个 ASIN × 每 ASIN ~13 条）
# --------------------------------------------------------------------------- #

_RESERVE_ASINS_FILE = CONFIG_DIR / "asins.reserve.txt"


def load_reserve_asins() -> tuple[str, ...]:
    """解析**备选** ASIN 池：环境变量 ``TABLEWARE_RESERVE_ASINS`` → ``config/asins.reserve.txt``。

    与 ``load_asins()`` 同一套解析规则（``#`` 注释、去重、保持顺序）。默认**空池** ——
    没配备选时，失败的目标位如实记为失败，而不是偷偷降条数。
    """
    env = _env_raw("TABLEWARE_RESERVE_ASINS")
    if env:
        raw_items = env.split(",")
    elif _RESERVE_ASINS_FILE.exists():
        raw_items = [
            line.split("#", 1)[0]
            for line in _RESERVE_ASINS_FILE.read_text(encoding="utf-8").splitlines()
        ]
    else:
        raw_items = []

    seen: dict[str, None] = {}
    for item in raw_items:
        asin = _normalize_asin(item)
        if asin:
            seen.setdefault(asin, None)
    return tuple(seen.keys())


RESERVE_ASINS: tuple[str, ...] = load_reserve_asins()
