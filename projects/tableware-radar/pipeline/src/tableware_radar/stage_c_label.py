"""阶段 C —— 封闭打标 + 两个闸门 + 三层降级（docs/ARCHITECTURE.md §5 T07 / PRD §8.4）。

这是把**真实评论**变成 ``labels`` 的唯一一环：上游 ``clean`` 产出 ``ReviewRecord``，
本模块逐条打标后回填 ``labels`` 与 ``labeling``，供 T08 聚合消费。

方法论（PRD §4.1 / §5.1）：

* **封闭编码**：只允许 ``config/dimensions.yaml`` 的枚举；落不进任何维度的进
  ``OTHER`` 并附自由话题短语（作为下一轮阶段 A 的输入）。
* **中英双语**：每条 label 必须带 ``evidence``（**英文原文、不翻译**）与
  ``dimension_name``（中文显示名，以 *dimensions.yaml* 为真源校正）。
* **每条记录必带 ``labeling.ok``**；``ok=false`` 必带 ``error``（R5）。

两个闸门（⚠️ **分母口径不同，禁止统一**，见 PRD §8.4「★ 三个分母」）：

====================  ====================  ==============================
闸门                  分子                  分母
====================  ====================  ==============================
① ``other`` 占比      ``other`` 维度条数     **只算 ``ok=true`` 条数**
② 打标失败率          ``ok=false`` 条数      **已发标条数**（``ok`` 真假都算）
====================  ====================  ==============================

任一闸门破线 → **立即中止**（``LabelRunResult.gate`` 非空），由 ``cli`` 落一份
**partial ``analysis.json``** 并写入 ``data_quality.gate``。

降级阶梯（ARCHITECTURE §4.3）：L0 调用级重试 → L1 校验失败走 ``build_repair``
修复式重试 → L2 批次失败**二分拆批**隔离坏条目；单条仍失败则 ``labeling.ok=false``
（**绝不静默丢弃**，计入闸门②分母）。``attempts`` 逐条可见。

**可测试性**：本模块只依赖 ``DshHeadlessClient`` 的 ``run_batch`` 契约，单测注入
``runner`` 假子进程即可离线跑通全流程（脚本见 ``tests/test_stage_c_label.py``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from . import config
from .dimensions import OTHER_DIMENSION_ID, DimensionSet
from .llm.client import BatchResult, DshHeadlessClient
from .llm.prompts import PromptLibrary
from .models import Analysis, Label, ReviewRecord

__all__ = [
    "GATE_OK",
    "GATE_OTHER_OVER_15PCT",
    "GATE_FAILURE_OVER_10PCT",
    "EVIDENCE_MAX_CHARS",
    "POLARITIES",
    "ERR_UNUSABLE",
    "ERR_GATE_ABORT",
    "GateEvaluation",
    "LabelStats",
    "LabelRunResult",
    "StageCLabeler",
    "evaluate_gates",
    "is_other_record",
    "build_partial_analysis",
    "label_records",
]

# ---- 闸门标识（写进 data_quality.gate）----

GATE_OK = ""                                        # 未破线（对外表现为 None）
GATE_OTHER_OVER_15PCT = "other_over_15pct"           # 闸门①
GATE_FAILURE_OVER_10PCT = "failure_over_10pct"       # 闸门②

# ---- 常量 ----

#: ``evidence`` 为英文原文片段的上限（与阶段 C Prompt 的契约一致，见 prompts.py）。
EVIDENCE_MAX_CHARS = 160
#: 允许的极性取值（PRD §5.1）。
POLARITIES = ("pos", "neg", "neutral", "mixed")
#: 未送标的两种原因 —— 用于把「没发标」与「发标失败」区分开（闸门② 只看后者）。
ERR_UNUSABLE = "unusable_review"
ERR_GATE_ABORT = "gate_abort_not_labeled"

_POLARITY_SET = frozenset(POLARITIES)
_OTHER_NAME = "其他"


# --------------------------------------------------------------------------- #
# 闸门判读
# --------------------------------------------------------------------------- #

@dataclass
class GateEvaluation:
    """一次闸门判读的结果（pilot 与全量各算一次）。"""

    scope: str = "full"                 # pilot | full
    sent_records: int = 0               # 已发标条数（闸门② 分母）
    ok_records: int = 0                 # ok=true（闸门① 分母）
    failed_records: int = 0             # ok=false
    other_records: int = 0              # other 维度条数（闸门① 分子）
    other_ratio: float = 0.0            # = other_records / ok_records
    failure_rate: float = 0.0           # = failed_records / sent_records
    other_gate_max: float = 0.0
    failure_gate_max: float = 0.0
    gate: Optional[str] = None          # None = 通过

    @property
    def tripped(self) -> bool:
        return self.gate is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "sent_records": self.sent_records,
            "ok_records": self.ok_records,
            "failed_records": self.failed_records,
            "other_records": self.other_records,
            "other_ratio": round(self.other_ratio, 6),
            "failure_rate": round(self.failure_rate, 6),
            "other_gate_max": self.other_gate_max,
            "failure_gate_max": self.failure_gate_max,
            "gate": self.gate,
        }


def _was_sent(record: ReviewRecord) -> bool:
    """该记录是否**真正发给过** LLM（决定它是否进闸门②分母）。

    以 ``labeling.sent`` 为准；对没有该键的旧记录回退看 ``attempts >= 1``。
    """
    labeling = record.labeling or {}
    if "sent" in labeling:
        return bool(labeling.get("sent"))
    try:
        return int(labeling.get("attempts", 0) or 0) >= 1
    except (TypeError, ValueError):
        return False


def is_other_record(record: ReviewRecord) -> bool:
    """该记录是否算「``other`` 维度打标条数」（闸门① 分子）。

    判读口径（PRD §8.4「``other`` 维度打标条数」）：**封闭枚举没能放下它** ——
    即它的 ``labels`` 非空、且**全部**是 ``OTHER``（一个已定义维度都没命中）。

    若一条记录既有已定义维度、又额外带 ``OTHER``，说明标签体系**确实**放下了它，
    不算 `other`；``labels == []`` 是"成功打标但无命中"，也不是 `other`
    （PRD §5.1 注：``labels: []`` 与"打标失败"长得一样，故二者都不计入此处）。
    """
    labels = record.labels or []
    if not labels:
        return False
    has_other = any(lbl.dimension == OTHER_DIMENSION_ID for lbl in labels)
    has_defined = any(lbl.dimension != OTHER_DIMENSION_ID for lbl in labels)
    return has_other and not has_defined


def evaluate_gates(
    records: Sequence[ReviewRecord],
    *,
    other_gate_max: Optional[float] = None,
    failure_gate_max: Optional[float] = None,
    scope: str = "full",
) -> GateEvaluation:
    """对 ``records`` 做一次闸门判读（纯函数，不中止、不写盘）。

    未**发出**的记录（不可用 / 因闸门中止而未打标）不进任何分母。
    两个分母**刻意不同**：``other`` 占比只除以 ``ok=true``；失败率除以全部已发标。
    """
    other_max = config.OTHER_GATE_MAX if other_gate_max is None else other_gate_max
    fail_max = config.FAILURE_GATE_MAX if failure_gate_max is None else failure_gate_max

    sent = [r for r in records if _was_sent(r)]
    ok = [r for r in sent if r.labeling_ok]
    failed = [r for r in sent if not r.labeling_ok]

    other_n = sum(1 for r in ok if is_other_record(r))
    other_ratio = (other_n / len(ok)) if ok else 0.0
    failure_rate = (len(failed) / len(sent)) if sent else 0.0

    gate: Optional[str] = None
    if ok and other_ratio > other_max:
        gate = GATE_OTHER_OVER_15PCT
    elif sent and failure_rate > fail_max:
        gate = GATE_FAILURE_OVER_10PCT

    return GateEvaluation(
        scope=scope,
        sent_records=len(sent),
        ok_records=len(ok),
        failed_records=len(failed),
        other_records=other_n,
        other_ratio=other_ratio,
        failure_rate=failure_rate,
        other_gate_max=other_max,
        failure_gate_max=fail_max,
        gate=gate,
    )


# --------------------------------------------------------------------------- #
# 结果载体
# --------------------------------------------------------------------------- #

@dataclass
class LabelStats:
    """一轮打标的统计（落 run.log / data_quality）。"""

    total_records: int = 0
    usable: int = 0
    sent: int = 0
    labeled_ok: int = 0
    labeled_failed: int = 0
    skipped_unusable: int = 0
    not_labeled_gate_abort: int = 0
    other_records: int = 0
    attempts_total: int = 0
    pilot_records: int = 0
    other_ratio: float = 0.0
    failure_rate: float = 0.0
    gate: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "usable": self.usable,
            "sent": self.sent,
            "labeled_ok": self.labeled_ok,
            "labeled_failed": self.labeled_failed,
            "skipped_unusable": self.skipped_unusable,
            "not_labeled_gate_abort": self.not_labeled_gate_abort,
            "other_records": self.other_records,
            "attempts_total": self.attempts_total,
            "pilot_records": self.pilot_records,
            "other_ratio": round(self.other_ratio, 6),
            "failure_rate": round(self.failure_rate, 6),
            "gate": self.gate,
        }


@dataclass
class LabelRunResult:
    """一轮阶段 C 的完整产出。"""

    records: list[ReviewRecord]
    stats: LabelStats
    gate: Optional[str] = None
    pilot: Optional[GateEvaluation] = None
    full: Optional[GateEvaluation] = None
    dimension_set_version: str = ""
    prompt_version: str = ""

    @property
    def aborted(self) -> bool:
        """是否因闸门破线而中止。"""
        return self.gate is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stats": self.stats.to_dict(),
            "gate": self.gate,
            "aborted": self.aborted,
            "pilot": self.pilot.to_dict() if self.pilot else None,
            "full": self.full.to_dict() if self.full else None,
            "dimension_set_version": self.dimension_set_version,
            "prompt_version": self.prompt_version,
        }


# --------------------------------------------------------------------------- #
# 打标器
# --------------------------------------------------------------------------- #

class StageCLabeler:
    """把清洗后的 ``ReviewRecord`` 逐条打成封闭枚举标签。

    ``client`` 只需满足 ``DshHeadlessClient`` 的 ``run_batch`` 契约（鸭子类型），
    故单测可注入 ``runner`` 假子进程离线运行。
    """

    def __init__(
        self,
        client: DshHeadlessClient,
        dims: DimensionSet,
        *,
        prompts: Optional[PromptLibrary] = None,
        batch_size: Optional[int] = None,
        pilot_size: Optional[int] = None,
        other_gate_max: Optional[float] = None,
        failure_gate_max: Optional[float] = None,
        model_name: Optional[str] = None,
        labeled_at: Optional[str] = None,
    ) -> None:
        if not dims.by_id:
            # 空枚举会让所有评论落到 OTHER，闸门① 必然破线 —— 不如立刻说清楚。
            raise ValueError("维度集合为空，无法进行阶段 C 打标（请先固化 dimensions.yaml）。")

        self.client = client
        self.dims = dims
        self.prompts = prompts or PromptLibrary()
        self.batch_size = batch_size if batch_size is not None else config.LLM_BATCH_SIZE
        self.pilot_size = pilot_size if pilot_size is not None else config.PILOT_SIZE
        self.other_gate_max = (
            other_gate_max if other_gate_max is not None else config.OTHER_GATE_MAX
        )
        self.failure_gate_max = (
            failure_gate_max if failure_gate_max is not None else config.FAILURE_GATE_MAX
        )
        self.model_name = model_name or f"dsh:{getattr(client, 'profile', config.LLM_PROFILE)}"
        self.labeled_at = labeled_at if labeled_at is not None else config.now_iso()
        self.stats = LabelStats()

    # ------------------------------------------------------------------ #
    # 主流程
    # ------------------------------------------------------------------ #
    def run(self, records: Sequence[ReviewRecord]) -> LabelRunResult:
        """逐条打标并判读闸门。**只在通过 pilot 闸门后才继续全量**。"""
        materialized = list(records)
        self.stats = LabelStats(total_records=len(materialized))

        # 不可用记录不送标（省成本）；显式标成"没发标"，避免留在 pending 态。
        usable: list[ReviewRecord] = []
        for record in materialized:
            if record.is_usable:
                usable.append(record)
            else:
                record.labels = []
                record.labeling = {**self._meta(), "ok": False, "error": ERR_UNUSABLE,
                                  "sent": False}
        self.stats.usable = len(usable)
        self.stats.skipped_unusable = len(materialized) - len(usable)

        if not usable:
            self.stats.other_ratio = 0.0
            self.stats.failure_rate = 0.0
            return LabelRunResult(
                records=materialized, stats=self.stats,
                dimension_set_version=self.dims.version, prompt_version=self.prompts.prompt_version,
            )

        # ---- 阶段 1：pilot 探路（成本护栏）----
        pilot = list(usable) if self.pilot_size <= 0 else usable[: self.pilot_size]
        self.stats.pilot_records = len(pilot)
        self._label(pilot)
        pilot_eval = self._evaluate(pilot, scope="pilot")

        if pilot_eval.tripped:
            # ★ 立即中止：剩下的 usable 记录**不送标**，保住的预算不烧。
            self._mark_aborted(usable[len(pilot):])
            self.stats.other_ratio = pilot_eval.other_ratio
            self.stats.failure_rate = pilot_eval.failure_rate
            self.stats.other_records = pilot_eval.other_records
            self.stats.gate = pilot_eval.gate
            return LabelRunResult(
                records=materialized, stats=self.stats, gate=pilot_eval.gate,
                pilot=pilot_eval, full=None,
                dimension_set_version=self.dims.version,
                prompt_version=self.prompts.prompt_version,
            )

        # ---- 阶段 2：全量收尾 ----
        rest = usable[len(pilot):]
        if rest:
            self._label(rest)

        full_eval = self._evaluate(usable, scope="full")
        self.stats.other_ratio = full_eval.other_ratio
        self.stats.failure_rate = full_eval.failure_rate
        self.stats.other_records = full_eval.other_records
        self.stats.gate = full_eval.gate

        return LabelRunResult(
            records=materialized, stats=self.stats, gate=full_eval.gate,
            pilot=pilot_eval, full=full_eval,
            dimension_set_version=self.dims.version, prompt_version=self.prompts.prompt_version,
        )

    # ------------------------------------------------------------------ #
    # 单批
    # ------------------------------------------------------------------ #
    def _label(self, records: list[ReviewRecord]) -> None:
        """把一批记录交给 ``run_batch``（内部自带二分拆批），回填结果。"""
        if not records:
            return
        payload = [self._payload(record) for record in records]

        def build_prompt(items: Sequence[dict[str, Any]]) -> str:
            return self.prompts.build_stage_c(list(items), list(self.dims.by_id.values()))

        results = self.client.run_batch(
            payload,
            build_prompt,
            batch_size=self.batch_size,
            validator=self._validate_output,
            repair=self._repair,
            halve_on_failure=True,
        )
        for result in results:
            # ``index`` 与传入的 payload 对齐 —— 比按 review_id 反查更稳（不怕重复 id）。
            record = records[result.index]
            self._apply(record, result)

    def _apply(self, record: ReviewRecord, result: BatchResult) -> None:
        """把一条 ``BatchResult`` 落到记录上（成功 / 失败都要留下痕迹）。"""
        self.stats.sent += 1
        self.stats.attempts_total += int(result.attempts or 0)

        if not result.ok:
            record.labels = []
            record.labeling = {
                **self._meta(), "ok": False,
                "error": (result.error or "unknown_error"),
                "sent": True, "attempts": int(result.attempts or 0), "labels_count": 0,
            }
            self.stats.labeled_failed += 1
            return

        try:
            labels = self._to_labels(result.value)
        except Exception as exc:  # noqa: BLE001 - 二次兜底：validator 过了仍可能形状不对
            record.labels = []
            record.labeling = {
                **self._meta(), "ok": False,
                "error": f"invalid_labels: {exc}",
                "sent": True, "attempts": int(result.attempts or 0), "labels_count": 0,
            }
            self.stats.labeled_failed += 1
            return

        record.labels = labels
        record.labeling = {
            **self._meta(), "ok": True, "error": "",
            "sent": True, "attempts": int(result.attempts or 0), "labels_count": len(labels),
        }
        self.stats.labeled_ok += 1

    # ------------------------------------------------------------------ #
    # 校验 / 修复（给 DshHeadlessClient 的回调）
    # ------------------------------------------------------------------ #
    def _validate_output(self, parsed: Any) -> None:
        """批次级校验：形状必须是「与输入等长、顺序一致的数组」。

        任一 label 缺 ``evidence`` / ``dimension_name``，或引用了未定义枚举，都抛错 ——
        由客户端的 L1 ``repair`` 先修，修不动再 L2 二分拆批隔离。
        """
        if not isinstance(parsed, list):
            raise ValueError(f"阶段 C 输出必须是 JSON 数组，实得 {type(parsed).__name__}")
        for index, item in enumerate(parsed):
            if not isinstance(item, dict):
                raise ValueError(f"第 {index + 1} 项不是 JSON 对象")
            labels = item.get("labels")
            if labels is None:
                raise ValueError(f"第 {index + 1} 项缺少 labels 字段")
            if not isinstance(labels, list):
                raise ValueError(f"第 {index + 1} 项的 labels 不是数组")
            for position, raw in enumerate(labels):
                self._validate_label_dict(index, position, raw)

    def _validate_label_dict(self, index: int, position: int, raw: Any) -> None:
        where = f"第 {index + 1} 项的第 {position + 1} 个 label"
        if not isinstance(raw, dict):
            raise ValueError(f"{where} 不是 JSON 对象")
        dimension = str(raw.get("dimension", "") or "").strip()
        value = str(raw.get("value", "") or "").strip()
        name = str(raw.get("dimension_name", "") or "").strip()
        evidence = str(raw.get("evidence", "") or "").strip()
        if not dimension:
            raise ValueError(f"{where} 缺少 dimension")
        if not value:
            raise ValueError(f"{where} 缺少 value")
        if not name:
            raise ValueError(f"{where} 缺少 dimension_name（中文显示名）")
        if not evidence:
            raise ValueError(f"{where} 缺少 evidence（英文原文，不得翻译）")
        if len(evidence) > EVIDENCE_MAX_CHARS:
            raise ValueError(f"{where} 的 evidence 超过 {EVIDENCE_MAX_CHARS} 字符")
        self.dims.validate_label(dimension, value)   # 未定义维度 / 越界枚举 → DimensionError

    def _repair(self, task: str, error: str, previous_output: str) -> str:
        """L1 修复式重试：只补正、不发明（复用原 task，不重新拼 prompt）。"""
        return self.prompts.build_repair_from_task("c", task, error, previous_output)

    # ------------------------------------------------------------------ #
    # 转换
    # ------------------------------------------------------------------ #
    def _to_labels(self, value: Any) -> list[Label]:
        """把 LLM 输出的一条记录转成 ``Label`` 列表（含真源校正与兜底裁剪）。"""
        if not isinstance(value, dict):
            raise ValueError("记录不是 JSON 对象")
        raw_labels = value.get("labels", [])
        if not isinstance(raw_labels, list):
            raise ValueError("labels 不是数组")

        labels: list[Label] = []
        for raw in raw_labels:
            if not isinstance(raw, dict):
                raise ValueError("label 不是 JSON 对象")
            dimension = str(raw.get("dimension", "") or "").strip().upper()
            enum_value = str(raw.get("value", "") or "").strip()
            self.dims.validate_label(dimension, enum_value)

            # ★ 中文名以 dimensions.yaml 为真源校正（LLM 抄错/漏抄都不影响正确性）。
            if dimension == OTHER_DIMENSION_ID:
                name = str(raw.get("dimension_name", "") or "").strip() or _OTHER_NAME
            else:
                name = self.dims.name_of(dimension)

            evidence = str(raw.get("evidence", "") or "").strip()[:EVIDENCE_MAX_CHARS]

            labels.append(Label(
                dimension=dimension,
                dimension_name=name,
                value=enum_value,
                polarity=self._normalize_polarity(raw.get("polarity")),
                confidence=self._normalize_confidence(raw.get("confidence")),
                evidence=evidence,
            ))
        return labels

    @staticmethod
    def _normalize_polarity(raw: Any) -> str:
        value = str(raw or "").strip().lower()
        return value if value in _POLARITY_SET else "neutral"

    @staticmethod
    def _normalize_confidence(raw: Any) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, value))

    def _payload(self, record: ReviewRecord) -> dict[str, str]:
        """送进 Prompt 的字段：标题取原文，正文取**清洗后**文本（已去 HTML/UI 噪声）。"""
        return {
            "review_id": record.review_id,
            "title": str(record.raw.get("title", "") or ""),
            "body": str(record.content.get("text", "") or ""),
        }

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    def _meta(self) -> dict[str, Any]:
        """每条 ``labeling`` 共有的元数据。"""
        return {
            "model": self.model_name,
            "prompt_version": self.prompts.prompt_version,
            "dimension_set_version": self.dims.version,
            "labeled_at": self.labeled_at,
        }

    def _mark_aborted(self, records: list[ReviewRecord]) -> None:
        """闸门破了之后，没来得及打标的记录显式标记为「未送标」。"""
        for record in records:
            record.labels = []
            record.labeling = {**self._meta(), "ok": False, "error": ERR_GATE_ABORT, "sent": False}
        self.stats.not_labeled_gate_abort += len(records)

    def _evaluate(self, records: Sequence[ReviewRecord], *, scope: str) -> GateEvaluation:
        return evaluate_gates(
            records,
            other_gate_max=self.other_gate_max,
            failure_gate_max=self.failure_gate_max,
            scope=scope,
        )


# --------------------------------------------------------------------------- #
# 便捷入口
# --------------------------------------------------------------------------- #

def label_records(
    records: Sequence[ReviewRecord],
    dims: DimensionSet,
    client: DshHeadlessClient,
    **kwargs: Any,
) -> LabelRunResult:
    """一次性打标（无状态便捷入口）。"""
    return StageCLabeler(client, dims, **kwargs).run(records)


def build_partial_analysis(
    result: LabelRunResult,
    dims: DimensionSet,
    *,
    reports: Optional[list[Any]] = None,
    titles: Optional[dict[str, str]] = None,
    generated_at: Optional[str] = None,
) -> Analysis:
    """把（可能是中止的）打标结果聚合成一份 **partial ``analysis.json``**。

    闸门破线时把 ``gate`` 写进 ``data_quality.gate`` —— 这正是 PRD §8.4 要求的
    「立即中止并落 partial ``analysis.json`` + ``gate`` 标记」。落盘由 ``cli`` 负责。
    """
    from .aggregate import aggregate  # 延迟导入：避免 aggregate ↔ stage_c 的顶层耦合

    analysis = aggregate(
        list(result.records), dims,
        reports=reports, titles=titles, generated_at=generated_at,
    )
    if result.gate:
        analysis.data_quality = {**analysis.data_quality, "gate": result.gate}
    return analysis
