"""T05 验收测试：阶段 A 开放编码（**全离线**）。

用一个「假子进程 runner」驱动**真实**的 ``DshHeadlessClient.run_batch``，因此
批量切分、L0 重试、L1 修复式重试、L2 二分拆批、``attempts`` 计数全部走真实代码路径，
只有 ``node`` 调用被换掉 —— 不联网、不调 LLM。

覆盖验收点（ARCHITECTURE §5 T05）：
* 每 ASIN 抽 10 条；不足则用其全部并**如实记进统计**（不悄悄少抽）；
* 产出 ``{claim_text, topic_phrase, sentiment, source_review_id}``（字段恰好齐全）；
* **Prompt 禁止归类**（不得出现任何已定义维度）；
* ``source_review_id`` 以清洗记录为真源校正；
* **可复现**（同输入同输出）；不可用记录不抽样、不送标。
"""

from __future__ import annotations

import json

from tableware_radar import config
from tableware_radar.dimensions import REQUIRED_DIMENSION_IDS
from tableware_radar.llm.client import DshHeadlessClient
from tableware_radar.models import ReviewRecord
from tableware_radar.stage_a_topics import (
    SENTIMENTS,
    TopicDiscoverer,
    discover_topics,
    write_raw_topics,
)

# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #


def _rec(review_id: str, asin: str = "A", *, usable: bool = True, text: str | None = None) -> ReviewRecord:
    """造一条清洗后的记录。``usable=False`` 即视为「不可用」（过短噪声）。"""
    return ReviewRecord(
        review_id=review_id,
        asin=asin,
        source={"url": f"https://x/dp/{asin}", "fetcher_version": "0.1.0"},
        raw={"title": "Sturdy plates", "body": "Sturdy plates", "rating": 4, "review_date": "2026-01-01"},
        content={
            "text": text if text is not None else ("sturdy plates that survived the dishwasher " * 3),
            "is_usable": usable,
        },
        labels=[],
        labeling={"ok": False, "error": "pending_labeling", "attempts": 0},
    )


# ---- 假子进程：只解析 INPUT REVIEWS 那段 JSON，避免把 EXAMPLE / 修复回的旧输出捞进来 ----

_INPUT_ANCHOR = "INPUT REVIEWS ("


def _ids_in(task: str) -> list[str]:
    anchor = task.find(_INPUT_ANCHOR)
    if anchor < 0:
        return []
    start = task.find("[", anchor)
    if start < 0:
        return []
    try:
        items, _end = json.JSONDecoder().raw_decode(task[start:])
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    return [str(item.get("review_id", "")) for item in items if isinstance(item, dict)]


def _stdout(
    ids: list[str],
    *,
    sentiment: str = "neg",
    topic_phrase: str = "dishwasher durability",
    claim_text: str | None = None,
    source_review_id: str | None = None,
) -> str:
    """为给定 review_id 生成一份**合规**的阶段 A 输出。"""
    items = []
    for rid in ids:
        items.append({
            "claim_text": claim_text if claim_text is not None else f"plates chip after washing ({rid})",
            "topic_phrase": topic_phrase,
            "sentiment": sentiment,
            "source_review_id": source_review_id if source_review_id is not None else rid,
        })
    return json.dumps(items, ensure_ascii=False)


class Runner:
    """可脚本化的假 runner（签名与 ``DshHeadlessClient`` 期望的一致）。"""

    def __init__(self, policy):
        self.policy = policy
        self.calls: list[list[str]] = []

    def __call__(self, task, timeout):  # noqa: ANN001 - runner 协议
        ids = _ids_in(task)
        self.calls.append(ids)
        return self.policy(ids, task, self)

    @property
    def sent_ids(self) -> list[str]:
        return [rid for call in self.calls for rid in call]


def _client(runner: Runner, **kwargs) -> DshHeadlessClient:
    kwargs.setdefault("max_retries", 0)
    return DshHeadlessClient(runner=runner, **kwargs)


def _ok_policy(ids, task, self):  # noqa: ANN001
    return 0, _stdout(ids), ""


# --------------------------------------------------------------------------- #
# Prompt 禁止归类
# --------------------------------------------------------------------------- #

def test_stage_a_prompt_forbids_categorization():
    discoverer = TopicDiscoverer(_client(Runner(_ok_policy)))
    batch = [{"review_id": "R1", "title": "Plates", "body": "they chip easily"}]
    task = discoverer.prompts.build_stage_a(batch)

    assert "Do NOT classify" in task            # 显式禁令
    assert "There is no category list" in task
    # 阶段 A 不得向 Prompt 泄漏任何已定义维度（归类会污染发现）
    for dim_id in REQUIRED_DIMENSION_IDS:
        assert dim_id not in task, f"阶段 A Prompt 不应出现维度 {dim_id}"


# --------------------------------------------------------------------------- #
# 抽样
# --------------------------------------------------------------------------- #

def test_samples_ten_per_asin():
    records = []
    for asin in ("A", "B", "C"):
        records.extend(_rec(f"{asin}{i:02d}", asin=asin) for i in range(15))
    runner = Runner(_ok_policy)

    discoverer = TopicDiscoverer(_client(runner), sample_per_asin=10)
    topics = discoverer.discover(records)

    assert discoverer.stats.asins == 3
    assert discoverer.stats.sampled == 30
    assert discoverer.stats.actual_sample == {"A": 10, "B": 10, "C": 10}
    assert discoverer.stats.underfilled_asins == []
    assert len(topics) == 30
    assert discoverer.stats.sent == 30
    assert discoverer.stats.ok == 30
    assert discoverer.stats.failed == 0


def test_underfilled_asin_uses_all_and_notes_actual_count():
    """不足 10 条则用其全部，并**如实记进统计**（不得悄悄少抽也不得凑数）。"""
    records = [_rec(f"A{i:02d}", asin="A") for i in range(4)]          # 只有 4 条
    records += [_rec(f"B{i:02d}", asin="B") for i in range(12)]
    runner = Runner(_ok_policy)

    discoverer = TopicDiscoverer(_client(runner), sample_per_asin=10)
    topics = discoverer.discover(records)

    assert discoverer.stats.actual_sample == {"A": 4, "B": 10}
    assert discoverer.stats.underfilled_asins == ["A"]
    assert discoverer.stats.sampled == 14
    assert len(topics) == 14
    # 该 ASIN 的 4 条全在里面（用其全部）
    a_ids = {t["source_review_id"] for t in topics if t["source_review_id"].startswith("A")}
    assert a_ids == {f"A{i:02d}" for i in range(4)}


def test_unusable_records_are_never_sampled_or_sent():
    records = [_rec(f"R{i}") for i in range(3)]
    records += [_rec("U1", usable=False, text="x"), _rec("U2", usable=False, text="y")]
    runner = Runner(_ok_policy)

    discoverer = TopicDiscoverer(_client(runner), sample_per_asin=10)
    topics = discoverer.discover(records)

    assert discoverer.stats.usable == 3
    assert "U1" not in runner.sent_ids and "U2" not in runner.sent_ids
    assert {t["source_review_id"] for t in topics} == {"R0", "R1", "R2"}


# --------------------------------------------------------------------------- #
# 输出 schema
# --------------------------------------------------------------------------- #

def test_each_topic_has_exactly_the_required_fields():
    records = [_rec(f"R{i}") for i in range(4)]
    discoverer = TopicDiscoverer(_client(Runner(_ok_policy)), sample_per_asin=10)
    topics = discoverer.discover(records)

    assert topics
    for topic in topics:
        assert set(topic.keys()) == {"claim_text", "topic_phrase", "sentiment", "source_review_id"}
        assert topic["claim_text"]
        assert topic["topic_phrase"]
        assert topic["sentiment"] in SENTIMENTS


def test_sentiment_is_normalized():
    records = [_rec("R1")]
    runner = Runner(lambda ids, task, self: (0, _stdout(ids, sentiment="NEG"), ""))
    topics = TopicDiscoverer(_client(runner), sample_per_asin=10).discover(records)
    assert topics[0]["sentiment"] == "neg"


def test_source_review_id_is_corrected_from_record():
    """LLM 抄错 id 也无所谓 —— 真源是清洗记录。"""
    records = [_rec("R1"), _rec("R2")]
    runner = Runner(lambda ids, task, self: (0, _stdout(ids, source_review_id="WRONG-ID"), ""))
    topics = TopicDiscoverer(_client(runner), sample_per_asin=10).discover(records)
    assert {t["source_review_id"] for t in topics} == {"R1", "R2"}


def test_long_claim_is_truncated_defensively():
    records = [_rec("R1")]
    runner = Runner(lambda ids, task, self: (0, _stdout(ids, claim_text="x" * 500), ""))
    topics = TopicDiscoverer(_client(runner), sample_per_asin=10).discover(records)
    assert len(topics[0]["claim_text"]) == 200


# --------------------------------------------------------------------------- #
# 校验 / 修复 / 降级
# --------------------------------------------------------------------------- #

def test_missing_topic_phrase_is_repaired_before_giving_up():
    """L1：第一次输出不合规（缺 topic_phrase）→ 带 REJECTED 的修复 task 重试 → 成功。"""
    records = [_rec("R1")]
    bad = json.dumps([{"claim_text": "chips", "topic_phrase": "", "sentiment": "neg",
                       "source_review_id": "R1"}], ensure_ascii=False)
    seen = {"repaired": 0}

    def policy(ids, task, self):  # noqa: ANN001
        if "REJECTED" in task:
            seen["repaired"] += 1
            return 0, _stdout(ids), ""
        return 0, bad, ""

    runner = Runner(policy)
    topics = TopicDiscoverer(_client(runner, max_retries=1), sample_per_asin=10).discover(records)

    assert seen["repaired"] == 1
    assert len(topics) == 1 and topics[0]["topic_phrase"]
    assert runner.calls  # 确实重试过


def test_binary_split_isolates_one_poison_record():
    """L2：整批失败时二分拆批，只有坏条目失败，其余照常成功，且**不静默丢弃**。"""
    records = [_rec(f"R{i:02d}") for i in range(12)]

    def policy(ids, task, self):  # noqa: ANN001
        if "R05" in ids:
            return 1, "", "poison record"
        return 0, _stdout(ids), ""

    runner = Runner(policy)
    discoverer = TopicDiscoverer(_client(runner), sample_per_asin=12, batch_size=12)
    topics = discoverer.discover(records)

    assert discoverer.stats.ok == 11
    assert discoverer.stats.failed == 1
    assert discoverer.stats.failures[0]["review_id"] == "R05"
    assert "R05" not in {t["source_review_id"] for t in topics}
    # 真的发生了二分（出现了小于整批的中间批次）
    assert any(len(ids) == 6 for ids in runner.calls)


def test_invalid_sentiment_is_rejected_by_validator():
    records = [_rec("R1")]
    bad = json.dumps([{"claim_text": "chips", "topic_phrase": "durability",
                       "sentiment": "sometimes", "source_review_id": "R1"}], ensure_ascii=False)
    runner = Runner(lambda ids, task, self: (0, bad, ""))
    discoverer = TopicDiscoverer(_client(runner), sample_per_asin=10)
    topics = discoverer.discover(records)

    assert topics == []
    assert discoverer.stats.failed == 1
    assert "sentiment" in discoverer.stats.failures[0]["error"]


# --------------------------------------------------------------------------- #
# 可复现 / 边界
# --------------------------------------------------------------------------- #

def test_same_input_yields_same_output():
    records = [_rec(f"A{i:02d}", asin="A") for i in range(12)]
    records += [_rec(f"B{i:02d}", asin="B") for i in range(12)]

    first = TopicDiscoverer(_client(Runner(_ok_policy)), sample_per_asin=10).discover(records)
    second = TopicDiscoverer(_client(Runner(_ok_policy)), sample_per_asin=10).discover(records)
    assert first == second


def test_empty_input_is_safe():
    called: list[list[str]] = []
    runner = Runner(lambda ids, task, self: (called.append(ids), (0, "[]", ""))[1])
    topics = TopicDiscoverer(_client(runner), sample_per_asin=10).discover([])
    assert topics == []
    assert called == []


def test_all_unusable_input_is_safe():
    records = [_rec("U1", usable=False, text="x")]
    runner = Runner(_ok_policy)
    discoverer = TopicDiscoverer(_client(runner), sample_per_asin=10)
    topics = discoverer.discover(records)
    assert topics == []
    assert runner.sent_ids == []
    assert discoverer.stats.sampled == 0


# --------------------------------------------------------------------------- #
# 落盘 / 便捷入口
# --------------------------------------------------------------------------- #

def test_write_raw_topics_writes_jsonl(tmp_path):
    topics = [
        {"claim_text": "a", "topic_phrase": "durability", "sentiment": "neg", "source_review_id": "R1"},
        {"claim_text": "b", "topic_phrase": "cleaning", "sentiment": "pos", "source_review_id": "R2"},
    ]
    path = write_raw_topics(topics, tmp_path / "topics" / "raw_topics.jsonl")

    assert path.exists()
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert lines == topics
    for line in lines:
        assert set(line.keys()) == {"claim_text", "topic_phrase", "sentiment", "source_review_id"}


def test_default_topics_path_is_under_data_topics():
    path = write_raw_topics([])
    assert path == config.TOPICS_DIR / "raw_topics.jsonl"
    assert path.exists()


def test_discover_topics_convenience_returns_stats():
    records = [_rec(f"R{i}") for i in range(3)]
    topics, stats = discover_topics(records, _client(Runner(_ok_policy)), sample_per_asin=10)
    assert len(topics) == 3
    assert stats.ok == 3
    assert stats.sampled == 3
    assert stats.prompt_version.startswith("prompt-")
