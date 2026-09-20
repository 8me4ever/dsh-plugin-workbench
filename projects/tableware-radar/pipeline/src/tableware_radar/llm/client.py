"""``DshHeadlessClient`` —— 通过 dsh headless 子进程调用本机 DeepSeek。

实现要点（docs/ARCHITECTURE.md §1.3 / §1.4）：

* 命令用 **``node <dsh bin.js>``**（而非 ``dsh.cmd``）以规避 Windows ``.cmd`` 引号地狱；
  任务文本作为**单个 argv 元素**传入（含换行安全，已实测）。
* **stdout / stderr 分开捕获**，只解析 stdout；stderr（推理增量）写入
  ``data/logs/labeling.log`` 供排障。
* **批量提交**：单批 15–20 条；任务文本长度封顶 ``config.LLM_TASK_CHAR_LIMIT``（规避
  Windows 32767 命令行上限）。
* 三层降级：L0 调用级重试（超时/非零退出/无 JSON，``attempts++``）；L1 解析级修复式重试
  （``validator`` + ``repair`` 回调）；L2 批次级二分拆批（``run_batch``）。

**可测试性**：真正的子进程调用被抽象为可注入的 ``runner``（默认走 ``subprocess``）。
单测注入 fake runner 即可覆盖超时/非零退出/坏 JSON 三类失败，无需真实 dsh。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from .. import config

__all__ = [
    "LlmError",
    "LlmTimeoutError",
    "LlmProcessError",
    "LlmParseError",
    "LlmEnvironmentError",
    "BatchResult",
    "extract_json",
    "find_node",
    "find_dsh_entry",
    "DshHeadlessClient",
]

# runner 契约：``runner(task, timeout_s) -> (returncode, stdout, stderr)``，可抛 ``LlmError``。
Runner = Callable[[str, float], "tuple[int, str, str]"]
# repair 回调：``repair(task, error, raw_output) -> 新的 task``。
RepairFn = Callable[[str, str, str], str]
Validator = Callable[[Any], None]


# --------------------------------------------------------------------------- #
# 异常
# --------------------------------------------------------------------------- #

class LlmError(RuntimeError):
    """LLM 调用相关错误基类。"""


class LlmTimeoutError(LlmError):
    """子进程超时。"""


class LlmProcessError(LlmError):
    """非零退出码。"""


class LlmParseError(LlmError):
    """stdout 无法解析为 JSON，或未通过校验。"""


class LlmEnvironmentError(LlmError):
    """环境级错误（找不到 node/dsh、profile 无法初始化）——应快速失败。"""


# --------------------------------------------------------------------------- #
# 环境探测
# --------------------------------------------------------------------------- #

def find_node() -> str:
    """定位 ``node`` 可执行文件（PATH → ``NODE_EXE`` 环境变量）。"""
    exe = os.environ.get("NODE_EXE") or shutil.which("node")
    if not exe:
        raise LlmEnvironmentError(
            "未找到 node。请确认已安装 Node.js 且在 PATH 中，或设置环境变量 NODE_EXE 指向 node。"
        )
    return exe


def find_dsh_entry() -> str:
    """定位 dsh 的 JS 入口 ``@deepseek-ai/dsh/lib/bin.js``。

    与工作台 ``scripts/dev.mjs`` 的 ``findDshEntry()`` 同源：优先 ``npm root -g``，
    回退 ``%APPDATA%/npm/node_modules/...``。
    """
    candidates: list[Path] = []
    npm = shutil.which("npm")
    if npm:
        try:
            proc = subprocess.run(
                [npm, "root", "-g"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                candidates.append(
                    Path(proc.stdout.strip()) / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
                )
        except Exception:  # noqa: BLE001 - npm 探测失败则继续其他候选
            pass
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(
            Path(appdata) / "npm" / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
        )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise LlmEnvironmentError(
        "未找到 dsh。请先安装：npm i -g @deepseek-ai/dsh（或设置 DSH_ENTRY 指向 bin.js）。"
    )


# --------------------------------------------------------------------------- #
# JSON 健壮抽取
# --------------------------------------------------------------------------- #

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*")


def extract_json(text: Optional[str]) -> Any:
    """从可能夹带 markdown fence / 前后说明的文本中抽取 JSON 值。

    步骤：去 fence → 整体 ``json.loads`` → 逐位置 ``raw_decode`` 兜底。
    全程失败则抛 ``LlmParseError``。
    """
    if text is None:
        raise LlmParseError("stdout 为空")
    stripped = text.strip()
    if not stripped:
        raise LlmParseError("stdout 为空")

    # 去掉首尾代码围栏
    stripped = _FENCE_RE.sub("", stripped)
    stripped = re.sub(r"```$", "", stripped).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(stripped[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise LlmParseError(f"stdout 不包含可解析的 JSON（前 200 字符：{stripped[:200]!r}）")


# --------------------------------------------------------------------------- #
# 批次结果
# --------------------------------------------------------------------------- #

@dataclass
class BatchResult:
    """``run_batch`` 的单条结果（与输入 items 对齐）。"""

    index: int
    item: Any
    ok: bool
    value: Any = None
    error: str = ""
    attempts: int = 0


# --------------------------------------------------------------------------- #
# 客户端
# --------------------------------------------------------------------------- #

class DshHeadlessClient:
    """dsh headless 子进程 LLM 客户端。"""

    def __init__(
        self,
        profile: Optional[str] = None,
        *,
        timeout_s: Optional[int] = None,
        warmup_timeout_s: Optional[int] = None,
        max_retries: Optional[int] = None,
        node_exe: Optional[str] = None,
        dsh_entry: Optional[str] = None,
        runner: Optional[Runner] = None,
        log_path: Optional[str | Path] = None,
    ) -> None:
        self.profile = profile or config.LLM_PROFILE
        self._timeout_s = float(timeout_s if timeout_s is not None else config.LLM_TIMEOUT_S)
        self._warmup_timeout_s = float(
            warmup_timeout_s if warmup_timeout_s is not None else config.LLM_WARMUP_TIMEOUT_S
        )
        self._max_retries = max_retries if max_retries is not None else config.LLM_MAX_RETRIES
        self._node_exe = node_exe or os.environ.get("NODE_EXE")
        self._dsh_entry = dsh_entry or os.environ.get("DSH_ENTRY")
        self._runner = runner
        self._log_path = str(log_path) if log_path is not None else str(config.LOGS_DIR / "labeling.log")
        self.last_attempts: int = 0

    # ---- 生命周期 ----
    def ensure_profile(self, timeout_s: Optional[int] = None) -> None:
        """暖机：空跑一次，把首次 212s 冷启动成本显式前置。

        失败即抛 ``LlmEnvironmentError`` 并给出可复制的修复命令（快速失败，绝不产出空数据）。
        """
        timeout = float(timeout_s if timeout_s is not None else self._warmup_timeout_s)
        try:
            returncode, _stdout, stderr = self._run("ok", timeout)
        except LlmError as exc:
            raise LlmEnvironmentError(self._env_hint(str(exc))) from exc
        self._log_stderr(stderr)
        if returncode != 0:
            raise LlmEnvironmentError(self._env_hint(f"暖机非零退出：{returncode}"))

    # ---- 单次调用 ----
    def run_json_with_attempts(
        self,
        task: str,
        *,
        timeout_s: Optional[int] = None,
        max_retries: Optional[int] = None,
        validator: Optional[Validator] = None,
        repair: Optional[RepairFn] = None,
    ) -> tuple[Any, int]:
        """调用一次 dsh 并解析 JSON，返回 ``(值, attempts)``。

        * L0：超时/非零退出/无 JSON —— 重试同一 task（``attempts++``）。
        * L1：JSON 合法但 ``validator`` 不过 —— 若有 ``repair`` 则用其改写 task 后重试。
        """
        timeout = float(timeout_s if timeout_s is not None else self._timeout_s)
        retries = self._max_retries if max_retries is None else max_retries
        max_attempts = max(1, retries + 1)

        current_task = task
        attempts = 0
        last_error: Optional[LlmError] = None

        while attempts < max_attempts:
            attempts += 1
            try:
                stdout = self._invoke(current_task, timeout)
            except LlmError as exc:
                last_error = exc
                continue  # L0 重试同一 task
            try:
                value = extract_json(stdout)
                if validator is not None:
                    validator(value)
            except (LlmParseError, ValueError, AssertionError) as exc:
                last_error = exc if isinstance(exc, LlmError) else LlmParseError(str(exc))
                if repair is not None:
                    try:
                        current_task = repair(task, str(exc), stdout)
                    except Exception:  # noqa: BLE001 - repair 自身失败则保持原 task 重试
                        current_task = task
                continue  # L1 修复式重试
            self.last_attempts = attempts
            return value, attempts

        self.last_attempts = attempts
        raise last_error or LlmParseError("未知失败")

    def run_json(
        self,
        task: str,
        timeout_s: Optional[int] = None,
        max_retries: Optional[int] = None,
        *,
        validator: Optional[Validator] = None,
        repair: Optional[RepairFn] = None,
    ) -> Any:
        """``run_json_with_attempts`` 的薄封装，只返回解析值。"""
        value, _attempts = self.run_json_with_attempts(
            task, timeout_s=timeout_s, max_retries=max_retries, validator=validator, repair=repair
        )
        return value

    # ---- 批量调用 ----
    def run_batch(
        self,
        items: Sequence[Any],
        build_prompt: Callable[[Sequence[Any]], str],
        *,
        batch_size: Optional[int] = None,
        on_item: Optional[Callable[[BatchResult], None]] = None,
        validator: Optional[Validator] = None,
        repair: Optional[RepairFn] = None,
        halve_on_failure: bool = True,
    ) -> list[BatchResult]:
        """把 ``items`` 分批提交，返回与输入对齐的 ``BatchResult`` 列表。

        批次失败（L2）时若 ``halve_on_failure`` 则**二分拆批**递归隔离坏条目，
        单条仍失败则记为 ``ok=False``（**不静默丢弃**，由上层计入分母）。
        """
        materialized = list(items)
        budget = batch_size if batch_size is not None else config.LLM_BATCH_SIZE
        budget = max(1, int(budget))

        results: list[BatchResult] = []
        for pairs in self._chunk_indexed(materialized, budget, build_prompt):
            results.extend(
                self._process_batch(
                    pairs, build_prompt, on_item, validator, repair, halve_on_failure
                )
            )
        results.sort(key=lambda r: r.index)
        return results

    # ---- 内部 ----
    def _process_batch(
        self,
        pairs: list[tuple[int, Any]],
        build_prompt: Callable[[Sequence[Any]], str],
        on_item: Optional[Callable[[BatchResult], None]],
        validator: Optional[Validator],
        repair: Optional[RepairFn],
        halve_on_failure: bool,
    ) -> list[BatchResult]:
        batch_items = [item for _idx, item in pairs]
        task = build_prompt(batch_items)
        attempts = 0
        try:
            parsed, attempts = self.run_json_with_attempts(
                task, validator=validator, repair=repair
            )
            if not isinstance(parsed, list) or len(parsed) != len(batch_items):
                got = len(parsed) if isinstance(parsed, list) else type(parsed).__name__
                raise LlmParseError(f"批次输出条数不匹配：期望 {len(batch_items)}，实得 {got}")
            out: list[BatchResult] = []
            for (index, item), value in zip(pairs, parsed):
                result = BatchResult(index=index, item=item, ok=True, value=value, attempts=attempts)
                if on_item:
                    on_item(result)
                out.append(result)
            return out
        except LlmError as exc:
            if halve_on_failure and len(pairs) > 1:
                mid = len(pairs) // 2
                return self._process_batch(
                    pairs[:mid], build_prompt, on_item, validator, repair, halve_on_failure
                ) + self._process_batch(
                    pairs[mid:], build_prompt, on_item, validator, repair, halve_on_failure
                )
            out = []
            for index, item in pairs:
                result = BatchResult(
                    index=index, item=item, ok=False, value=None,
                    error=str(exc), attempts=attempts or self.last_attempts,
                )
                if on_item:
                    on_item(result)
                out.append(result)
            return out

    def _chunk_indexed(
        self,
        items: list[Any],
        budget: int,
        build_prompt: Callable[[Sequence[Any]], str],
    ) -> list[list[tuple[int, Any]]]:
        """按条数 + 字符预算切分，返回带原始下标的批次。"""
        chunks: list[list[tuple[int, Any]]] = []
        current: list[tuple[int, Any]] = []
        for index, item in enumerate(items):
            current.append((index, item))
            too_many = len(current) >= budget
            too_long = len(build_prompt([it for _i, it in current])) > config.LLM_TASK_CHAR_LIMIT
            if too_many or too_long:
                if len(current) > 1:
                    last = current.pop()
                    chunks.append(current)
                    current = [last]
                else:
                    chunks.append(current)
                    current = []
        if current:
            chunks.append(current)
        return chunks

    def _invoke(self, task: str, timeout: float) -> str:
        returncode, stdout, stderr = self._run(task, timeout)
        self._log_stderr(stderr)
        if returncode != 0:
            raise LlmProcessError(f"dsh 非零退出（exit={returncode}）：{stderr.strip()[-400:]}")
        return stdout

    def _run(self, task: str, timeout: float) -> tuple[int, str, str]:
        if self._runner is not None:
            return self._runner(task, timeout)
        node = self._node_exe or find_node()
        entry = self._dsh_entry or find_dsh_entry()
        cmd = [node, entry, "--profile", self.profile, task]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise LlmTimeoutError(f"dsh 调用超时（{timeout:.0f}s）") from exc
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def _log_stderr(self, stderr: str) -> None:
        if not stderr or not stderr.strip():
            return
        try:
            path = Path(self._log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n----- {config.now_iso()} -----\n{stderr}\n")
        except Exception:  # noqa: BLE001 - 日志失败不得影响主流程
            pass

    def _env_hint(self, detail: str) -> str:
        return (
            f"无法初始化 dsh headless profile：{detail}\n"
            "修复步骤（可直接复制执行）：\n"
            "  1) npm i -g @deepseek-ai/dsh\n"
            "  2) 确认 node 在 PATH（或设置 NODE_EXE）\n"
            f"  3) dsh --profile {self.profile} \"ok\"   # 首次会初始化 profile（约 212s）"
        )
