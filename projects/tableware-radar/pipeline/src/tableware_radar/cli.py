"""端到端编排 CLI（docs/ARCHITECTURE.md §5 T09 / 时序图 4.1）。

一条命令跑通全链路::

    python -m tableware_radar.cli run --all

链路：**抓取 → 清洗 → 阶段 A（开放编码）→ 阶段 C（封闭打标 + 闸门）→ 聚合**
（``data/analysis.json`` 为页面唯一真源）。

设计要点（T09 验收）：

* **前置检查（快速失败，PRD §8.2）**：``config/dimensions.yaml``
  - 不存在 → 提示「以 ``dimensions.example.yaml`` 为起点复制一份」；
  - 存在但 ``validate()`` 不过 → **拒绝执行**；
  两种情况打印的都是**可直接复制执行的命令**。
* **任一步失败都给可复制修复命令**：每步失败抛 ``PipelineError``（带 ``fix`` 字段），
  ``main`` 统一打印 ``[失败] …`` 与「可复制执行的修复命令」。
* **可注入**：``fetcher`` / ``client`` / ``paths`` / ``sleeper`` 等均可注入，
  故单测能在**离线、零等待**下跑通全链路（见 ``tests/test_cli.py``）。
* **错误处理**（§7）：阶段级失败**非零退出**并打印修复命令，**不吞异常**。

子命令：

* ``run``（默认）—— ``--all`` 全链路；``--only fetch|clean|a|c|aggregate`` 只跑到该步（含）。
* ``discover`` —— 按关键词搜索、过滤并分层抽样，产出待确认商品清单。
* ``doctor`` —— 环境自检（node / dsh / dimensions.yaml / ASIN 清单），不联网。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from . import config
from .clean import Cleaner
from .dimensions import DimensionError, DimensionSet, load_dimension_set
from .discovery import YahooAmazonUkDiscovery, write_manifest
from .fetch import AmazonUkRun, get_fetcher
from .llm.client import DshHeadlessClient, LlmError
from .llm.prompts import PromptLibrary
from .models import Analysis
from .stage_a_topics import TopicDiscoverer, write_raw_topics
from .stage_c_label import StageCLabeler, build_partial_analysis

__all__ = [
    "STAGES",
    "PipelineError",
    "PipelinePaths",
    "Pipeline",
    "build_parser",
    "main",
]

#: 有序阶段（``--only`` 取前缀）。
STAGES: tuple[str, ...] = ("fetch", "clean", "a", "c", "aggregate")

#: LLM 环境未就绪时的可复制修复命令。
_LLM_FIX = "npm i -g @deepseek-ai/dsh"
#: 抓取依赖缺失（真实抓取需 scrapling）时的可复制修复命令。
_DEPS_FIX = "pip install -r pipeline/requirements.txt"
#: 全链路重跑命令（多数步骤失败的兜底修复）。
_RERUN_FIX = "python -m tableware_radar.cli run --all"

#: 判定「依赖缺失」的错误特征串（小写匹配）——命中即给 pip 修复命令，而非误导性的网络排查。
_DEPENDENCY_MARKERS = ("modulenotfounderror", "importerror", "no module named")


# --------------------------------------------------------------------------- #
# 异常
# --------------------------------------------------------------------------- #

class PipelineError(RuntimeError):
    """管道某一步失败；``fix`` 为**可直接复制执行**的修复命令。"""

    def __init__(self, message: str, *, fix: str = "", stage: str = "") -> None:
        super().__init__(message)
        self.fix = fix
        self.stage = stage


# --------------------------------------------------------------------------- #
# 落盘路径
# --------------------------------------------------------------------------- #

@dataclass
class PipelinePaths:
    """链路各步的落盘位置（默认取自 ``config``；测试可整体重定向到临时目录）。"""

    raw_dir: Path = config.RAW_DIR
    fetch_report_file: Path = config.FETCH_REPORT_PATH
    clean_file: Path = config.CLEAN_DIR / "reviews.jsonl"
    topics_file: Path = config.TOPICS_DIR / "raw_topics.jsonl"
    labeled_file: Path = config.LABELED_DIR / "labeled.jsonl"
    analysis_file: Path = config.ANALYSIS_PATH


# --------------------------------------------------------------------------- #
# 管道
# --------------------------------------------------------------------------- #

class Pipeline:
    """把各阶段串成一条可测试的链路（对应架构类图的 ``Pipeline``）。

    各 ``stage_*`` 方法在内部捕获异常并转成带 ``fix`` 的 ``PipelineError``；
    阶段之间的中间产物保存在实例属性上（``fetch_run`` / ``records`` / ``topics`` /
    ``label_result`` / ``analysis``），便于 ``--only`` 分段调试与断言。
    """

    def __init__(
        self,
        *,
        fetcher: Any,
        client: DshHeadlessClient,
        dims: DimensionSet,
        asins: Optional[Sequence[str]] = None,
        reserves: Optional[Sequence[str]] = None,
        paths: Optional[PipelinePaths] = None,
        prompts: Optional[PromptLibrary] = None,
        batch_size: Optional[int] = None,
        pilot_size: Optional[int] = None,
        sample_per_asin: Optional[int] = None,
        sleeper: Optional[Any] = None,
        jitter: Optional[Any] = None,
        now: Optional[Any] = None,
        generated_at: Optional[str] = None,
    ) -> None:
        self.fetcher = fetcher
        self.client = client
        self.dims = dims
        self.asins: tuple[str, ...] = tuple(asins) if asins else config.ASINS
        self.reserves: tuple[str, ...] = (
            tuple(reserves) if reserves is not None else config.RESERVE_ASINS
        )
        self.paths = paths or PipelinePaths()
        self.prompts = prompts or PromptLibrary()
        self.batch_size = batch_size
        self.pilot_size = pilot_size
        self.sample_per_asin = sample_per_asin
        self._sleeper = sleeper
        self._jitter = jitter
        self.now = now
        self.generated_at = generated_at

        # ---- 阶段间中间产物 ----
        self.fetch_run: Optional[Any] = None
        self.records: list[Any] = []
        self.topics: list[dict[str, str]] = []
        self.label_result: Optional[Any] = None
        self.analysis: Optional[Analysis] = None

    # ------------------------------------------------------------------ #
    # 主流程
    # ------------------------------------------------------------------ #
    def run_all(self, *, only: Optional[str] = None, warmup: bool = True) -> Optional[Analysis]:
        """按序跑链路；``only`` 非空时只跑到该步（含）。

        返回**聚合结果**（跑到 ``aggregate`` 时）；未跑到则返回 ``None``。
        闸门破线时 ``stage_aggregate`` 会先落 partial ``analysis.json`` 再抛 ``PipelineError``。
        """
        if only is not None and only not in STAGES:
            raise ValueError(f"未知阶段 {only!r}（可选：{', '.join(STAGES)}）")
        steps = STAGES if only is None else STAGES[: STAGES.index(only) + 1]

        if "fetch" in steps:
            self.stage_fetch()
        if "clean" in steps:
            self.stage_clean()
        if warmup and any(step in steps for step in ("a", "c")):
            self._ensure_profile()
        if "a" in steps:
            self.stage_a()
        if "c" in steps:
            self.stage_c()
        if "aggregate" in steps:
            return self.stage_aggregate()
        return None

    # ------------------------------------------------------------------ #
    # 各阶段
    # ------------------------------------------------------------------ #
    def stage_fetch(self) -> Any:
        """抓取全部目标 ASIN（重试 / 退避 / 换备选 / 窗口截断）并落盘。"""
        run = AmazonUkRun(
            self.fetcher,
            targets=self.asins,
            reserves=self.reserves,
            sleeper=self._sleeper,
            jitter=self._jitter,
            now=self.now,
            generated_at=self.generated_at,
        )
        try:
            self.fetch_run = run.fetch_all()
            self.fetch_run.persist(
                raw_dir=self.paths.raw_dir,
                report_path=self.paths.fetch_report_file,
            )
        except PipelineError:
            raise
        except Exception as exc:  # noqa: BLE001 - 抓取层任何异常都转成带修复命令的失败
            raise PipelineError(
                f"抓取阶段失败：{type(exc).__name__}: {exc}",
                fix="python -m tableware_radar.cli run --only fetch",
                stage="fetch",
            ) from exc

        if not self.fetch_run.reviews:
            # ★ 病因要报对方向：缺依赖 ≠ 网络问题（见 _fetch_empty_error）。
            raise _fetch_empty_error(self.fetch_run)
        return self.fetch_run

    def stage_clean(self) -> list[Any]:
        """清洗去重（含 24 个月窗口兜底丢弃），落 ``reviews.jsonl``。"""
        fetcher_version = self.fetch_run.fetcher_version if self.fetch_run else config.FETCHER_VERSION
        cleaner = Cleaner(fetcher_version=fetcher_version)
        try:
            self.records = cleaner.clean(self.fetch_run.reviews, now=self.now)
        except Exception as exc:  # noqa: BLE001
            raise PipelineError(
                f"清洗阶段失败：{type(exc).__name__}: {exc}",
                fix="python -m tableware_radar.cli run --only clean",
                stage="clean",
            ) from exc

        self.clean_stats = cleaner.stats
        _write_jsonl(self.paths.clean_file, [r.to_dict() for r in self.records])

        if not self.records:
            raise PipelineError(
                "清洗后无任何记录（可能全部落在 24 个月窗口外，或正文均为噪声）。",
                fix="python -m tableware_radar.cli run --only fetch",
                stage="clean",
            )
        return self.records

    def stage_a(self) -> list[dict[str, str]]:
        """阶段 A 开放编码（每 ASIN 抽样 → claim + topic_phrase），落 ``raw_topics.jsonl``。"""
        discoverer = TopicDiscoverer(
            self.client,
            prompts=self.prompts,
            sample_per_asin=self.sample_per_asin,
            batch_size=self.batch_size,
        )
        try:
            self.topics = discoverer.discover(self.records)
        except LlmError as exc:
            raise PipelineError(
                f"阶段 A（LLM）调用失败：{exc}",
                fix=_LLM_FIX,
                stage="a",
            ) from exc

        self.topic_stats = discoverer.stats
        write_raw_topics(self.topics, self.paths.topics_file)

        if self.topic_stats.sampled > 0 and self.topic_stats.ok == 0:
            raise PipelineError(
                f"阶段 A 全部失败（{self.topic_stats.sampled} 条抽样，0 条成功）。",
                fix=_LLM_FIX,
                stage="a",
            )
        return self.topics

    def stage_c(self) -> Any:
        """阶段 C 封闭打标（pilot → 闸门 → 全量），落 ``labeled.jsonl``。"""
        labeler = StageCLabeler(
            self.client,
            self.dims,
            prompts=self.prompts,
            batch_size=self.batch_size,
            pilot_size=self.pilot_size,
        )
        try:
            self.label_result = labeler.run(self.records)
        except LlmError as exc:
            raise PipelineError(
                f"阶段 C（LLM）调用失败：{exc}",
                fix=_LLM_FIX,
                stage="c",
            ) from exc

        self.label_stats = self.label_result.stats
        _write_jsonl(self.paths.labeled_file, [r.to_dict() for r in self.label_result.records])
        return self.label_result

    def stage_aggregate(self) -> Analysis:
        """聚合打分 → 落 ``analysis.json``；闸门破线时落 partial 后抛 ``PipelineError``。"""
        if self.label_result is None:
            raise PipelineError(
                "尚未执行阶段 C，无法聚合。",
                fix=_RERUN_FIX,
                stage="aggregate",
            )
        analysis = build_partial_analysis(
            self.label_result,
            self.dims,
            reports=self.fetch_run.reports if self.fetch_run else None,
            generated_at=self.generated_at,
        )
        self.analysis = analysis
        _write_json(self.paths.analysis_file, analysis.to_dict())

        if self.label_result.gate:
            raise PipelineError(
                f"闸门破线（gate={self.label_result.gate}）：已落 partial analysis.json，"
                "停止全量打标 —— 回到阶段 B 核对/补充 config/dimensions.yaml 或修 Prompt。",
                fix=_RERUN_FIX,
                stage="gate",
            )
        return analysis

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _ensure_profile(self) -> None:
        """一次性暖机（吸收 dsh 首次 ~212s 冷启动）；失败即快速失败。"""
        try:
            self.client.ensure_profile()
        except LlmError as exc:
            raise PipelineError(
                f"LLM 环境未就绪：{exc}",
                fix=_LLM_FIX,
                stage="llm-env",
            ) from exc


# --------------------------------------------------------------------------- #
# 落盘工具
# --------------------------------------------------------------------------- #

def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# 抓取失败的病因判读
# --------------------------------------------------------------------------- #

def _is_dependency_error(error: str) -> bool:
    """该抓取错误是否是「依赖缺失」（如未安装 ``scrapling``）。"""
    lowered = (error or "").lower()
    return any(marker in lowered for marker in _DEPENDENCY_MARKERS)


def _fetch_empty_error(fetch_run: Any) -> PipelineError:
    """抓取零产出时**报对病因**并给出真正能修好的命令。

    * **依赖缺失**（``ModuleNotFoundError`` / ``ImportError``）→ ``pip install -r …``；
    * 否则（网络 / 池耗尽）→ 如实列出 per-ASIN 错误，并给「重试抓取」命令。

    无论哪支，都把 per-ASIN 的 ``FetchReport.error`` **原文透传**进消息，避免把用户
    带向错误方向（team-lead 复验：曾把「缺 scrapling」误导为「查网络/ASIN」）。
    """
    errors = [o.error for o in fetch_run.outcomes if getattr(o, "error", "")]
    errors += [o.report.error for o in fetch_run.outcomes if getattr(o.report, "error", "")]
    detail = "；".join(dict.fromkeys(e for e in errors if e)) or "无 per-ASIN 错误信息"

    if any(_is_dependency_error(e) for e in errors):
        return PipelineError(
            f"抓取依赖缺失（真实抓取 amazon_uk 需要 scrapling）：{detail}",
            fix=_DEPS_FIX,
            stage="fetch-deps",
        )
    return PipelineError(
        f"抓取未拿到任何窗口内评论（检查网络 / config/asins.txt / 备选池）。"
        f"per-ASIN 错误：{detail}",
        fix="python -m tableware_radar.cli run --only fetch",
        stage="fetch",
    )


# --------------------------------------------------------------------------- #
# 前置检查
# --------------------------------------------------------------------------- #

def load_dimensions_precheck() -> DimensionSet:
    """加载并校验 ``config/dimensions.yaml``；不合规抛带修复命令的 ``PipelineError``。

    * 不存在 → 提示「以示例为起点复制」（附 ``copy`` 命令）；
    * 存在但 ``validate()`` 不过 → 拒绝执行（附同一 ``copy`` 命令）。
    """
    path = config.DIMENSIONS_PATH
    example = config.DIMENSIONS_EXAMPLE_PATH
    copy_cmd = f'copy "{example}" "{path}"'

    if not path.exists():
        raise PipelineError(
            f"未找到 dimensions.yaml（{path}）。请先以示例为起点复制一份，再按阶段 B 固化维度。",
            fix=copy_cmd,
            stage="precheck-missing",
        )
    try:
        return load_dimension_set(path)
    except DimensionError as exc:
        raise PipelineError(
            f"dimensions.yaml 校验未通过，拒绝执行：{exc}",
            fix=copy_cmd,
            stage="precheck-invalid",
        ) from exc


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tableware_radar.cli",
        description="餐盘碗碟机会雷达 · 端到端离线数据管道",
    )
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="跑通全链路（默认 = run --all）")
    run.add_argument(
        "--all",
        action="store_true",
        help="跑通 fetch → clean → A → C → aggregate 全链路（默认行为）",
    )
    run.add_argument(
        "--only",
        choices=list(STAGES),
        default=None,
        help="只跑到该步（含）：fetch | clean | a | c | aggregate",
    )

    discover = sub.add_parser("discover", help="按关键词发现 Amazon UK 代表性商品（不启动评论分析）")
    discover.add_argument("--keyword", required=True, help="英文细分品类关键词，例如 ceramic pasta bowls")
    discover.add_argument("--count", type=int, default=10, choices=range(8, 11), metavar="8..10", help="样本数（8–10，默认 10）")
    discover.add_argument("--min-reviews", type=int, default=100, help="最低评论量（默认 100）")
    discover.add_argument("--output", default=None, help="待确认 JSON 路径；默认写入 data/discovery/<关键词>.json")

    sub.add_parser("doctor", help="环境自检：node / dsh / dimensions.yaml / ASIN 清单（不联网）")
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    fetcher: Any = None,
    client: Optional[DshHeadlessClient] = None,
    paths: Optional[PipelinePaths] = None,
    dims: Optional[DimensionSet] = None,
    asins: Optional[Sequence[str]] = None,
    reserves: Optional[Sequence[str]] = None,
    prompts: Optional[PromptLibrary] = None,
    batch_size: Optional[int] = None,
    pilot_size: Optional[int] = None,
    sample_per_asin: Optional[int] = None,
    sleeper: Optional[Any] = None,
    jitter: Optional[Any] = None,
    now: Optional[Any] = None,
    generated_at: Optional[str] = None,
    discovery: Any = None,
) -> int:
    """CLI 入口；返回进程退出码（0 成功 / 1 步骤失败 / 2 前置检查不过）。

    关键字参数是**注入缝**：测试传入 ``fetcher`` / ``client`` / ``paths`` / ``sleeper``
    等即可离线、零等待地跑通全链路。
    """
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    command = getattr(args, "command", None) or "run"

    if command == "doctor":
        return _doctor()

    if command == "discover":
        keyword = str(args.keyword).strip()
        slug = "-".join(part for part in keyword.lower().split() if part)
        output = Path(args.output) if args.output else config.DATA_DIR / "discovery" / f"{slug}.json"
        engine = discovery if discovery is not None else YahooAmazonUkDiscovery()
        try:
            manifest = engine.discover(keyword, count=args.count, min_reviews=args.min_reviews)
            write_manifest(manifest, output)
        except Exception as exc:  # noqa: BLE001 - CLI keeps discovery failures actionable
            return _fail(PipelineError(
                f"商品发现失败：{type(exc).__name__}: {exc}",
                fix=f'python -m tableware_radar.cli discover --keyword "{keyword}"',
                stage="discover",
            ), code=1)
        print(f"[完成] 已从 {manifest.marketplace} 选出 {manifest.selected_count} 个代表性商品")
        print(f"       待确认清单：{output}")
        print("       确认 selected_asins 后再启动评论抓取；本命令不会自动运行分析。")
        return 0

    only = None if getattr(args, "all", False) else getattr(args, "only", None)

    # ---- 前置检查：dimensions.yaml（不存在 / 不合法都快速失败）----
    if dims is None:
        try:
            dims = load_dimensions_precheck()
        except PipelineError as exc:
            return _fail(exc, code=2)

    resolved_fetcher = fetcher if fetcher is not None else get_fetcher()
    resolved_client = client if client is not None else DshHeadlessClient()

    pipeline = Pipeline(
        fetcher=resolved_fetcher,
        client=resolved_client,
        dims=dims,
        asins=asins,
        reserves=reserves,
        paths=paths,
        prompts=prompts,
        batch_size=batch_size,
        pilot_size=pilot_size,
        sample_per_asin=sample_per_asin,
        sleeper=sleeper,
        jitter=jitter,
        now=now,
        generated_at=generated_at,
    )

    try:
        analysis = pipeline.run_all(only=only)
    except PipelineError as exc:
        return _fail(exc, code=1)

    if analysis is None:
        print(f"[完成] 已跑至阶段「{only}」；中间产物见 {pipeline.paths.raw_dir.parent}")
        return 0

    sample = analysis.sample
    print(f"[完成] analysis.json 已写入 {pipeline.paths.analysis_file}")
    print(
        f"       comments_usable={sample.get('comments_usable', 0)} "
        f"asins_with_data={sample.get('asins_with_data', 0)} "
        f"labeled_coverage={sample.get('labeled_coverage', 0.0)} "
        f"gate={analysis.data_quality.get('gate')}"
    )
    return 0


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #

def _doctor() -> int:
    """环境自检（**不联网、不调 LLM**），打印可复制修复命令。"""
    print("[doctor] 环境自检")
    ok = True

    # node / dsh
    try:
        from .llm.client import find_dsh_entry, find_node

        print(f"  node      : {find_node()}")
        print(f"  dsh entry : {find_dsh_entry()}")
    except Exception as exc:  # noqa: BLE001 - 自检工具，任何异常都只报不抛
        ok = False
        print(f"  [缺] node/dsh：{exc}")
        print(f"        修复：{_LLM_FIX}")

    # dimensions.yaml
    path = config.DIMENSIONS_PATH
    if not path.exists():
        ok = False
        print(f"  [缺] dimensions.yaml：{path}")
        print(f'        修复：copy "{config.DIMENSIONS_EXAMPLE_PATH}" "{path}"')
    else:
        try:
            dims = load_dimension_set(path)
            print(f"  dimensions.yaml : OK（{len(dims.by_id)} 维，version={dims.version}）")
        except DimensionError as exc:
            ok = False
            print(f"  [错] dimensions.yaml 校验未通过：{exc}")
            print(f'        修复：copy "{config.DIMENSIONS_EXAMPLE_PATH}" "{path}"')

    # 抓取依赖：真实抓取（amazon_uk）需 scrapling；fixture 不需要（纯 HTTP、无需浏览器）。
    fetcher_name = (config.FETCHER_NAME or "").strip().lower()
    needs_scrapling = fetcher_name == "amazon_uk"
    if importlib.util.find_spec("scrapling") is not None:
        print("  scrapling : OK")
    elif needs_scrapling:
        ok = False
        print(f"  [缺] scrapling（fetcher={fetcher_name} 的硬依赖；纯 HTTP 即够，无需浏览器）")
        print(f"        修复：{_DEPS_FIX}")
    else:
        print(f"  scrapling : 缺失（当前 fetcher={fetcher_name} 不需要）")

    # ASIN 清单
    print(f"  ASIN 清单 : {', '.join(config.ASINS) or '(空)'}")
    print(f"  备选池    : {', '.join(config.RESERVE_ASINS) or '(空)'}")

    print(f"[doctor] {'全部就绪' if ok else '存在问题，见上方修复命令'}")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# 失败输出
# --------------------------------------------------------------------------- #

def _fail(exc: PipelineError, *, code: int) -> int:
    """统一打印失败原因与**可复制执行**的修复命令，返回非零退出码。"""
    print(f"[失败] {exc}")
    if exc.fix:
        print("可复制执行的修复命令：")
        print(f"  {exc.fix}")
    return code


if __name__ == "__main__":  # pragma: no cover - 手动执行入口
    sys.exit(main())
