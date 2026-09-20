"""阶段 A —— 开放编码（docs/ARCHITECTURE.md §5 T05 / PRD §4.1、§5、§7.1）。

把清洗后的 ``ReviewRecord`` **抽样**后交给 LLM 做**自由话题发现**（open coding），
产出 ``data/topics/raw_topics.jsonl``，作为**阶段 B（人工把自由话题簇收敛为
``config/dimensions.yaml``，不外包给 LLM）**的输入。

三条硬约束（T05 验收，勿破）：

1. **抽样**：每 ASIN 抽 ``config.STAGE_A_SAMPLE_PER_ASIN``（默认 **10**）条；不足则用该
   ASIN 的**全部**可用条，并**如实记进统计**（``actual_sample``）——**绝不悄悄少抽**。
2. **禁止归类**：阶段 A 只发现 ``claim + topic_phrase``，**严禁**把评论归入既有维度
   （维度尚未固化，归类会污染发现）。Prompt 层显式禁止；本层**不向 Prompt 传任何维度枚举**。
3. **可复现**：抽样顺序确定（按 ASIN、``review_id`` 排序），**同输入同输出**。

产出 schema（每条一行 JSON，与架构 §3 / 时序图 4.1 严格一致）::

    {"claim_text": "...", "topic_phrase": "...", "sentiment": "pos|neg|neutral|mixed",
     "source_review_id": "..."}

``source_review_id`` 以**清洗记录**为真源校正（不信任 LLM 抄的 id）；``claim_text`` /
``topic_phrase`` 缺失即视为**不合格输出**，交由客户端的 L1 修复式重试 / L2 二分拆批处理。

**可测试性**：本模块只依赖 ``DshHeadlessClient`` 的 ``run_batch`` 契约，单测注入
``runner`` 假子进程即可离线跑通全流程（见 ``tests/test_stage_a_topics.py``）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from . import config
from .llm.client import BatchResult, DshHeadlessClient
from .llm.prompts import PromptLibrary
from .models import ReviewRecord

__all__ = [
    "SENTIMENTS",
    "CLAIM_MAX_CHARS",
    "TOPIC_MAX_CHARS",
    "TopicStats",
    "TopicDiscoverer",
    "discover_topics",
    "write_raw_topics",
]

# ---- 常量 ----

#: 允许的情感极性（与阶段 C Prompt 契约一致）。
SENTIMENTS = ("pos", "neg", "neutral", "mixed")
#: ``claim_text`` 上限（与阶段 A Prompt 的 ``<=200 chars`` 契约一致）。
CLAIM_MAX_CHARS = 200
#: ``topic_phrase`` 上限（Prompt 要求 2–5 词，这里给一个防御性硬顶）。
TOPIC_MAX_CHARS = 80

_SENTIMENT_SET = frozenset(SENTIMENTS)


# --------------------------------------------------------------------------- #
# 统计
# --------------------------------------------------------------------------- #

@dataclass
class TopicStats:
    """一轮开放编码的统计（落 run.log / 人工核对抽样量）。"""

    total_records: int = 0
    usable: int = 0
    asins: int = 0
    sampled: int = 0
    sent: int = 0
    ok: int = 0
    failed: int = 0
    attempts_total: int = 0
    sample_per_asin: int = 0
    prompt_version: str = ""
    #: 每个 ASIN 实际抽到的条数（< sample_per_asin 说明该 ASIN 可用条不足，已用其全部）。
    actual_sample: dict[str, int] = field(default_factory=dict)
    #: 打标失败的条目（**不静默丢弃**，留痕可查）。
    failures: list[dict[str, str]] = field(default_factory=list)

    @property
    def underfilled_asins(self) -> list[str]:
        """可用条数不足以抽满 ``sample_per_asin`` 的 ASIN（需在报告中注明实际条数）。"""
        if self.sample_per_asin <= 0:
            return []
        return [a for a, n in self.actual_sample.items() if n < self.sample_per_asin]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "usable": self.usable,
            "asins": self.asins,
            "sampled": self.sampled,
            "sent": self.sent,
            "ok": self.ok,
            "failed": self.failed,
            "attempts_total": self.attempts_total,
            "sample_per_asin": self.sample_per_asin,
            "actual_sample": dict(self.actual_sample),
            "underfilled_asins": self.underfilled_asins,
            "failures": list(self.failures),
            "prompt_version": self.prompt_version,
        }


# --------------------------------------------------------------------------- #
# 发现器
# --------------------------------------------------------------------------- #

class TopicDiscoverer:
    """对清洗后的记录做抽样 → 阶段 A 开放编码。

    ``client`` 只需满足 ``DshHeadlessClient`` 的 ``run_batch`` 契约（鸭子类型），
    故单测可注入 ``runner`` 假子进程离线运行。
    """

    def __init__(
        self,
        client: DshHeadlessClient,
        *,
        prompts: Optional[PromptLibrary] = None,
        sample_per_asin: Optional[int] = None,
        batch_size: Optional[int] = None,
        model_name: Optional[str] = None,
        discovered_at: Optional[str] = None,
    ) -> None:
        self.client = client
        self.prompts = prompts or PromptLibrary()
        self.sample_per_asin = (
            sample_per_asin if sample_per_asin is not None else config.STAGE_A_SAMPLE_PER_ASIN
        )
        self.batch_size = batch_size if batch_size is not None else config.LLM_BATCH_SIZE
        self.model_name = model_name or f"dsh:{getattr(client, 'profile', config.LLM_PROFILE)}"
        self.discovered_at = discovered_at if discovered_at is not None else config.now_iso()
        self.stats = TopicStats(sample_per_asin=self.sample_per_asin,
                                prompt_version=self.prompts.prompt_version)

    # ------------------------------------------------------------------ #
    # 主流程
    # ------------------------------------------------------------------ #
    def discover(
        self,
        records: Sequence[ReviewRecord],
        sample_per_asin: Optional[int] = None,
    ) -> list[dict[str, str]]:
        """抽样并开放编码，返回 ``[{claim_text, topic_phrase, sentiment, source_review_id}]``。

        返回顺序 = 抽样顺序（先按 ASIN 升序，再按 ``review_id`` 升序），**确定可复现**。
        打标失败的条目**不计入返回值**，但会留在 ``self.stats.failures`` 中可查。
        """
        per_asin = sample_per_asin if sample_per_asin is not None else self.sample_per_asin
        materialized = list(records)

        self.stats = TopicStats(
            total_records=len(materialized),
            sample_per_asin=per_asin,
            prompt_version=self.prompts.prompt_version,
        )

        sampled, actual = self._sample(materialized, per_asin)
        self.stats.usable = sum(1 for r in materialized if r.is_usable)
        self.stats.asins = len(actual)
        self.stats.sampled = len(sampled)
        self.stats.actual_sample = actual

        if not sampled:
            return []

        return self._discover_batch(sampled)

    # ------------------------------------------------------------------ #
    # 抽样
    # ------------------------------------------------------------------ #
    def _sample(
        self,
        records: list[ReviewRecord],
        per_asin: int,
    ) -> tuple[list[ReviewRecord], dict[str, int]]:
        """每 ASIN 抽 ``per_asin`` 条（不足用全部），顺序确定、可复现。

        只对 ``is_usable`` 的记录抽样（不可用记录不送标，也不占抽样名额）。
        ASIN 升序、ASIN 内按 ``review_id`` 升序 —— 保证**同输入同输出**。
        """
        by_asin: dict[str, list[ReviewRecord]] = {}
        for record in records:
            if record.is_usable:
                by_asin.setdefault(record.asin, []).append(record)

        sampled: list[ReviewRecord] = []
        actual: dict[str, int] = {}
        for asin in sorted(by_asin):
            pool = sorted(by_asin[asin], key=lambda r: r.review_id)
            picked = pool if per_asin <= 0 else pool[:per_asin]
            actual[asin] = len(picked)
            sampled.extend(picked)
        return sampled, actual

    # ------------------------------------------------------------------ #
    # 批次调用
    # ------------------------------------------------------------------ #
    def _discover_batch(self, records: list[ReviewRecord]) -> list[dict[str, str]]:
        """把抽到的记录交给 ``run_batch``（内部自带二分拆批），回填话题。"""
        if not records:
            return []
        payload = [self._payload(record) for record in records]

        def build_prompt(items: Sequence[dict[str, Any]]) -> str:
            return self.prompts.build_stage_a(list(items))

        results = self.client.run_batch(
            payload,
            build_prompt,
            batch_size=self.batch_size,
            validator=self._validate_output,
            repair=self._repair,
            halve_on_failure=True,
        )

        topics: list[dict[str, str]] = []
        for result in results:
            # ``index`` 与传入的 payload 对齐 —— 比按 review_id 反查更稳（不怕重复 id）。
            record = records[result.index]
            self.stats.sent += 1
            self.stats.attempts_total += int(result.attempts or 0)

            if not result.ok:
                self._record_failure(record, result.error or "unknown_error")
                continue
            try:
                topic = self._to_topic(result.value, record)
            except Exception as exc:  # noqa: BLE001 - 二次兜底：validator 过了仍可能形状不对
                self._record_failure(record, f"invalid_topic: {exc}")
                continue
            topics.append(topic)
            self.stats.ok += 1
        return topics

    # ------------------------------------------------------------------ #
    # 校验 / 修复（给 DshHeadlessClient 的回调）
    # ------------------------------------------------------------------ #
    def _validate_output(self, parsed: Any) -> None:
        """批次级校验：形状必须是「与输入等长、顺序一致的数组」。

        每条须含非空 ``claim_text`` / ``topic_phrase``、合法 ``sentiment``、非空
        ``source_review_id``。任一不合规即抛错 —— 由客户端的 L1 ``repair`` 先修，
        修不动再 L2 二分拆批隔离。
        """
        if not isinstance(parsed, list):
            raise ValueError(f"阶段 A 输出必须是 JSON 数组，实得 {type(parsed).__name__}")
        for index, item in enumerate(parsed):
            where = f"第 {index + 1} 项"
            if not isinstance(item, dict):
                raise ValueError(f"{where} 不是 JSON 对象")
            if not str(item.get("claim_text", "") or "").strip():
                raise ValueError(f"{where} 缺少 claim_text")
            if not str(item.get("topic_phrase", "") or "").strip():
                raise ValueError(f"{where} 缺少 topic_phrase")
            sentiment = str(item.get("sentiment", "") or "").strip().lower()
            if sentiment not in _SENTIMENT_SET:
                raise ValueError(f"{where} 的 sentiment 非法：{item.get('sentiment')!r}")
            if not str(item.get("source_review_id", "") or "").strip():
                raise ValueError(f"{where} 缺少 source_review_id")

    def _repair(self, task: str, error: str, previous_output: str) -> str:
        """L1 修复式重试：只补正、不发明（复用原 task，不重新拼 prompt）。"""
        return self.prompts.build_repair_from_task("a", task, error, previous_output)

    # ------------------------------------------------------------------ #
    # 转换
    # ------------------------------------------------------------------ #
    def _to_topic(self, value: Any, record: ReviewRecord) -> dict[str, str]:
        """把 LLM 输出的一条记录转成规范话题 dict（真源校正 + 防御性裁剪）。"""
        if not isinstance(value, dict):
            raise ValueError("话题记录不是 JSON 对象")
        claim = str(value.get("claim_text", "") or "").strip()
        topic = str(value.get("topic_phrase", "") or "").strip()
        if not claim:
            raise ValueError("缺少 claim_text")
        if not topic:
            raise ValueError("缺少 topic_phrase")
        return {
            "claim_text": claim[:CLAIM_MAX_CHARS],
            "topic_phrase": topic[:TOPIC_MAX_CHARS],
            "sentiment": self._normalize_sentiment(value.get("sentiment")),
            # ★ 真源校正：不管 LLM 抄成什么，一律用清洗记录的 review_id。
            "source_review_id": record.review_id,
        }

    @staticmethod
    def _normalize_sentiment(raw: Any) -> str:
        value = str(raw or "").strip().lower()
        return value if value in _SENTIMENT_SET else "neutral"

    def _payload(self, record: ReviewRecord) -> dict[str, str]:
        """送进 Prompt 的字段：标题取原文，正文取**清洗后**文本（已去 HTML/UI 噪声）。"""
        return {
            "review_id": record.review_id,
            "title": str(record.raw.get("title", "") or ""),
            "body": str(record.content.get("text", "") or ""),
        }

    def _record_failure(self, record: ReviewRecord, error: str) -> None:
        self.stats.failed += 1
        self.stats.failures.append({"review_id": record.review_id, "error": error})


# --------------------------------------------------------------------------- #
# 便捷入口 / 落盘
# --------------------------------------------------------------------------- #

def discover_topics(
    records: Sequence[ReviewRecord],
    client: DshHeadlessClient,
    **kwargs: Any,
) -> tuple[list[dict[str, str]], TopicStats]:
    """一次性开放编码（无状态便捷入口），返回 ``(话题列表, 统计)``。"""
    discoverer = TopicDiscoverer(client, **kwargs)
    topics = discoverer.discover(records)
    return topics, discoverer.stats


def write_raw_topics(
    topics: Sequence[dict[str, str]],
    path: str | Path | None = None,
) -> Path:
    """把话题列表写成 ``raw_topics.jsonl``（一行一条 JSON），返回落盘路径。

    默认落 ``config.TOPICS_DIR / raw_topics.jsonl``；目录不存在会自动创建。
    以**覆盖**方式写入（可重跑产物，见架构 §7「目录真源」）。
    """
    target = Path(path) if path is not None else config.TOPICS_DIR / "raw_topics.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for topic in topics:
            handle.write(json.dumps(topic, ensure_ascii=False) + "\n")
    return target
