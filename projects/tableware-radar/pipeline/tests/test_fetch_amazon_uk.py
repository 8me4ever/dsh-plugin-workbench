"""T04 验收测试：抓取编排（**全离线**，零网络）。

夹具是真货：``probe/artifacts/L1_http_product_B0157FD9MS.html`` 是探针抓下来的**真实**
Amazon UK 商品页（1.9MB，13 条 Top reviews）。测试把 ``ScraplingAmazonUkFetcher._get``
换成读本地 HTML，因此**解析、拦截检测、报告构造全部走真实代码路径**，只有 HTTP 被换掉。

覆盖验收点：
* 每 ASIN 产出评论 + 24 个月窗口外评论**不落盘**；
* ``fetch_report.json`` 记录「捕获条数 vs 平台上限 13」对比，使"是否抓全"可判读；
* 失败或不足 ``MIN_REVIEWS_PER_ASIN`` → **从备选池换 ASIN 重试**（不降条数、不转半自动），
  换选全程写入报告；
* 重试 / 指数退避；验证码 / 登录墙**不重试**，立即换 ASIN；
* 无翻页、无登录（只请求 ``/dp/<ASIN>``）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tableware_radar import config
from tableware_radar.fetch.amazon_uk import (
    BLOCK_MARKERS,
    AmazonUkRun,
    ScraplingAmazonUkFetcher,
    parse_reviews_from_html,
    product_url,
    write_raw_reviews,
)
from tableware_radar.models import RawReview

_REPO = Path(__file__).resolve().parents[2]

#: **入库**的小夹具：从探针真产物里抽出的 13 个真实评论节点（108KB），
#: 保证全新 clone 上离线测试也能跑。生成脚本见 ``probe/extract_fixture.py``。
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "amazon_uk_product_B0157FD9MS.html"
#: 探针真产物（1.9MB，被 .gitignore 忽略）—— 本地存在时用它交叉校验夹具的出处。
_PROBE_ARTIFACT = _REPO / "probe" / "artifacts" / "L1_http_product_B0157FD9MS.html"

#: 固定"现在" —— 让 24 个月窗口的断言与跑测试的日期无关。
#: （真产物里 2024-04-17 / 2024-02-08 两条会落在窗口外。）
_NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)

_EMPTY_HTML = "<html><body><div id='dp'><h1 id='productTitle'>x</h1></div></body></html>"
_BLOCK_HTML = f"<html><body><h4>{BLOCK_MARKERS[0]}</h4></body></html>"

_TARGET = "B000000TGT"
_RESERVE = "B000000RSV"


def _product_html() -> str:
    """读夹具 HTML（缺失时回退到探针真产物）。"""
    for path in (_FIXTURE, _PROBE_ARTIFACT):
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    raise FileNotFoundError(
        f"缺少 T04 夹具：{_FIXTURE}\n"
        "重新生成：python probe/extract_fixture.py（需先有 probe/artifacts/ 的真产物）"
    )


# --------------------------------------------------------------------------- #
# 离线 fetcher：复用真实解析逻辑，只把网络换成读本地文件
# --------------------------------------------------------------------------- #

class _FakeResponse:
    def __init__(self, html: str, status: int = 200) -> None:
        self.html_content = html
        self.status = status


class OfflineFetcher(ScraplingAmazonUkFetcher):
    """``ScraplingAmazonUkFetcher`` + 本地页面表（零网络、零 scrapling）。

    ``pages`` 给出 ``{asin: html}``；``plan`` 给出 ``{asin: [step, ...]}`` 做**逐次**控制，
    ``step`` 是 HTML 字符串或一个异常实例（模拟网络错误）。列表耗尽后重复最后一项。
    """

    version = "0.1.0-offline"

    def __init__(self, pages: dict[str, str], plan: dict[str, list] | None = None) -> None:
        super().__init__()
        self.pages = {k.upper(): v for k, v in pages.items()}
        self.plan = {k.upper(): list(v) for k, v in (plan or {}).items()}
        self.urls: list[str] = []

    def _get(self, url: str):  # noqa: ANN201 - 签名由父类约定
        self.urls.append(url)
        asin = url.rstrip("/").rsplit("/", 1)[-1].upper()
        step = self._next_step(asin)
        if isinstance(step, BaseException):
            raise step
        html = step if isinstance(step, str) else self.pages.get(asin)
        if html is None:
            return _FakeResponse(_EMPTY_HTML, status=404)
        return _FakeResponse(html, status=200)

    def _next_step(self, asin: str):  # noqa: ANN202
        queue = self.plan.get(asin)
        if not queue:
            return None
        if len(queue) == 1:
            return queue[0]
        return queue.pop(0)

    @property
    def requested_asins(self) -> list[str]:
        return [url.rstrip("/").rsplit("/", 1)[-1] for url in self.urls]


def _real_fetcher(**kwargs) -> OfflineFetcher:
    return OfflineFetcher({_TARGET: _product_html()}, **kwargs)


def _run(fetcher, *, targets=(_TARGET,), reserves=(), **kwargs):
    """跑一次编排，默认固定"现在"、零等待、确定性抖动。"""
    kwargs.setdefault("now", _NOW)
    kwargs.setdefault("generated_at", "2026-09-19T00:00:00Z")
    kwargs.setdefault("sleeper", lambda _s: None)          # 零等待
    kwargs.setdefault("jitter", lambda lo, _hi: lo)        # 确定性
    return AmazonUkRun(fetcher, targets=targets, reserves=reserves, **kwargs).fetch_all()


# --------------------------------------------------------------------------- #
# 解析：真产物
# --------------------------------------------------------------------------- #

def test_fixture_parses_thirteen_reviews():
    """夹具是**真货**：13 条真实评论，字段齐全。"""
    html = _product_html()
    reviews = parse_reviews_from_html(html, "B0157FD9MS")

    assert len(reviews) == 13                          # 与探针实测一致（平台首屏上限）
    assert all(r.review_id and r.rating and r.review_date for r in reviews)
    assert all(r.country for r in reviews)
    assert {r.rating for r in reviews} & {1, 2, 3, 4, 5}
    # 至少一条无 helpful_votes（无票节点不存在是常态）
    assert any(r.helpful_votes is None for r in reviews)
    # ★ 更正探针 REPORT 的「variant 0/13」：商品页 review 节点**确实**带
    #   `data-hook="format-strip"`，本商品 13/13 都是 "Size Name: 10.5 Inch"。
    #   字段契约仍可空（`Optional[str]`），只是"实测恒为 None"的说法不成立。
    assert {r.variant for r in reviews} == {"Size Name: 10.5 Inch"}


def test_fixture_matches_the_probe_artifact_when_present():
    """夹具是从探针真产物里抽出来的：本地有真产物时，两者的 review_id 必须一致。"""
    if not _PROBE_ARTIFACT.exists():
        pytest.skip("probe/artifacts/ 未入库（可重跑产物），跳过出处交叉校验")

    artifact = _PROBE_ARTIFACT.read_text(encoding="utf-8", errors="replace")
    from_artifact = parse_reviews_from_html(artifact, "B0157FD9MS")
    from_fixture = parse_reviews_from_html(_product_html(), "B0157FD9MS")

    assert [r.review_id for r in from_fixture] == [r.review_id for r in from_artifact]
    assert [r.review_date for r in from_fixture] == [r.review_date for r in from_artifact]


def test_fetcher_reports_captured_against_platform_cap():
    reviews, report = _real_fetcher().fetch_reviews(_TARGET, 100)
    assert len(reviews) == 13
    assert report.fetched == 13
    assert report.platform_cap == config.PLATFORM_CAP_PER_ASIN == 13
    assert report.ok is True
    assert report.error == ""
    assert report.attempts == 1


# --------------------------------------------------------------------------- #
# 24 个月窗口：窗口外**不落盘**
# --------------------------------------------------------------------------- #

def test_window_drops_out_of_window_reviews():
    run = _run(_real_fetcher())
    outcome = run.outcomes[0]

    assert outcome.captured == 13                      # 抓到 13
    assert outcome.in_window == 11                     # 只有 11 条在窗口内
    assert outcome.dropped_out_of_window == 2
    assert len(outcome.reviews) == 11
    assert all(r.review_date >= "2024-09-19" for r in outcome.reviews)


def test_out_of_window_reviews_are_never_persisted(tmp_path: Path):
    run = _run(_real_fetcher())
    run.persist(raw_dir=tmp_path, report_path=tmp_path / "fetch_report.json")

    payload = json.loads((tmp_path / f"raw_{_TARGET}.json").read_text(encoding="utf-8"))
    assert payload["count"] == 11
    ids = {r["review_id"] for r in payload["reviews"]}
    # 真实产物里日期 < 2024-09-19 的两条
    assert "R1VU6P949QZXXI" not in ids                  # 2024-04-17
    assert "R1W4JZG6ESAVMR" not in ids                  # 2024-02-08
    assert len(payload["reviews"]) == 11


# --------------------------------------------------------------------------- #
# fetch_report.json：捕获 vs 上限
# --------------------------------------------------------------------------- #

def test_fetch_report_is_judgeable_against_platform_cap():
    run = _run(_real_fetcher())
    report = run.to_report_dict()

    assert report["platform_cap_per_asin"] == 13
    assert report["min_reviews_per_asin"] == 10
    assert report["time_window_months"] == 24
    outcome = report["outcomes"][0]
    assert outcome["captured"] == 13
    assert outcome["in_window"] == 11
    assert outcome["captured_vs_cap"] == "13/13"        # ★ 是否抓全，一眼可读
    assert outcome["status"] == "captured"
    assert outcome["ok"] is True
    assert report["summary"]["full_capture_slots"] == 1
    assert report["summary"]["captured_total"] == 13
    assert report["summary"]["in_window_total"] == 11
    assert report["summary"]["dropped_out_of_window_total"] == 2


def test_report_is_deterministic():
    first = _run(_real_fetcher()).to_report_dict()
    second = _run(_real_fetcher()).to_report_dict()
    assert first == second


# --------------------------------------------------------------------------- #
# 重试 / 退避
# --------------------------------------------------------------------------- #

def test_network_error_is_retried_then_succeeds():
    html = _product_html()
    fetcher = OfflineFetcher({_TARGET: html}, plan={_TARGET: [ConnectionError("boom"), html]})

    run = _run(fetcher, max_attempts=3)
    outcome = run.outcomes[0]

    assert outcome.ok is True
    assert outcome.report.attempts == 2                 # 第 1 次网络错，第 2 次成功
    assert outcome.attempts == 2
    assert len(fetcher.urls) == 2


def test_backoff_grows_between_attempts():
    html = _product_html()
    fetcher = OfflineFetcher({_TARGET: html}, plan={_TARGET: [ConnectionError("1"), ConnectionError("2"), html]})

    seen_jitter: list[tuple[float, float]] = []

    def jitter(lo: float, hi: float) -> float:
        seen_jitter.append((lo, hi))
        return lo

    runner = AmazonUkRun(
        fetcher, targets=[_TARGET], max_attempts=3, min_delay_s=3.0, max_delay_s=8.0,
        backoff_factor=2.0, sleeper=lambda _s: None, jitter=jitter, now=_NOW,
    )
    run = runner.fetch_all()

    assert run.outcomes[0].report.attempts == 3
    # 退避上界随重试次数增长（第 2 次尝试→3s，第 3 次→6s），并被 MAX_DELAY 夹住
    assert seen_jitter == [(3.0, 3.0), (3.0, 6.0)]
    assert [kind for kind, _d in runner.sleep_log] == ["retry", "retry"]
    assert all(3.0 <= d <= 8.0 for _k, d in runner.sleep_log)


def test_slot_delay_is_observed_between_asins():
    html = _product_html()
    fetcher = OfflineFetcher({_TARGET: html, "B000000002": html, "B000000003": html})
    runner = AmazonUkRun(
        fetcher, targets=[_TARGET, "B000000002", "B000000003"],
        sleeper=lambda _s: None, jitter=lambda lo, _hi: lo, now=_NOW,
    )
    run = runner.fetch_all()

    assert len(run.outcomes) == 3
    # 3 个位次之间正好 2 次位间休眠（第一个位次前不等）
    assert [kind for kind, _d in runner.sleep_log] == ["slot", "slot"]


# --------------------------------------------------------------------------- #
# 硬墙：验证码 / 登录墙不重试
# --------------------------------------------------------------------------- #

def test_captcha_block_is_not_retried():
    fetcher = OfflineFetcher({_TARGET: _BLOCK_HTML})

    run = _run(fetcher, max_attempts=3)
    outcome = run.outcomes[0]

    assert len(fetcher.urls) == 1                       # ★ 不硬刚：只打了一次
    assert outcome.ok is False
    assert outcome.status == "failed"
    assert outcome.error.startswith("blocked:")
    assert outcome.captured == 0


# --------------------------------------------------------------------------- #
# 换 ASIN 池
# --------------------------------------------------------------------------- #

def test_swap_uses_reserve_and_records_it():
    html = _product_html()
    fetcher = OfflineFetcher({_TARGET: _EMPTY_HTML, _RESERVE: html})

    run = _run(fetcher, targets=[_TARGET], reserves=[_RESERVE], max_attempts=3)
    outcome = run.outcomes[0]

    # 目标打满 3 次仍拿不到，第 4 次换成备选
    assert fetcher.requested_asins == [_TARGET, _TARGET, _TARGET, _RESERVE]
    assert outcome.asin == _RESERVE
    assert outcome.requested_asin == _TARGET
    assert outcome.report.swapped_from == _TARGET      # ★ 换选全程可见
    assert outcome.status == "swapped"
    assert outcome.ok is True
    assert outcome.in_window == 11
    assert outcome.attempts == 4

    report = run.to_report_dict()
    assert report["reserves_used"] == [_RESERVE]
    assert report["reserve_pool_remaining"] == []
    assert report["summary"]["swapped_slots"] == 1
    # 备选位上的 raw 文件用的是**备选 ASIN** 命名
    assert set(run.by_asin()) == {_RESERVE}


def test_insufficient_reviews_is_not_accepted():
    """★ 不降条数：拿不到 10 条就是失败，绝不"凑合接受"。"""
    html = _product_html()
    fetcher = OfflineFetcher({_TARGET: html})

    run = _run(fetcher, limit=5, max_attempts=2, reserves=[])
    outcome = run.outcomes[0]

    assert outcome.captured == 5
    assert outcome.in_window == 5
    assert outcome.ok is False
    assert outcome.status == "failed"
    assert "insufficient_reviews" in outcome.error
    assert "5<10" in outcome.error
    # 重试了 2 次仍不行 → 如实失败，而不是把 5 条当成功收下
    assert outcome.attempts == 2
    assert run.to_report_dict()["summary"]["failed_slots"] == 1


def test_reserve_pool_exhausted_marks_failure():
    fetcher = OfflineFetcher({_TARGET: _EMPTY_HTML})

    run = _run(fetcher, targets=[_TARGET], reserves=[], max_attempts=2)
    report = run.to_report_dict()

    assert run.outcomes[0].status == "failed"
    assert run.outcomes[0].report.swapped_from is None
    assert report["summary"]["failed_slots"] == 1
    assert report["reserves_used"] == []


def test_reserve_is_not_reused_across_slots():
    html = _product_html()
    second = "B000000002"
    # 两个目标位都失败，只有一个备选 —— 第二位必须失败，不能复用同一个备选
    fetcher = OfflineFetcher({_TARGET: _EMPTY_HTML, second: _EMPTY_HTML, _RESERVE: html})

    run = _run(fetcher, targets=[_TARGET, second], reserves=[_RESERVE], max_attempts=1)
    first, last = run.outcomes

    assert first.status == "swapped" and first.asin == _RESERVE
    assert last.status == "failed"
    assert fetcher.requested_asins.count(_RESERVE) == 1


# --------------------------------------------------------------------------- #
# 口径：无翻页 / 无登录
# --------------------------------------------------------------------------- #

def test_only_product_page_urls_are_requested():
    fetcher = _real_fetcher()
    run = _run(fetcher)

    assert run.outcomes[0].ok is True
    assert fetcher.urls == [product_url(_TARGET)]
    for url in fetcher.urls:
        assert "/dp/" in url
        assert "product-reviews" not in url              # 评论页 = 登录墙，绝不请求
        assert "signin" not in url
        assert "pageNumber" not in url                   # 无翻页


# --------------------------------------------------------------------------- #
# 落盘
# --------------------------------------------------------------------------- #

def test_persist_writes_raw_files_and_report(tmp_path: Path):
    run = _run(_real_fetcher())
    written = run.persist(raw_dir=tmp_path, report_path=tmp_path / "fetch_report.json")

    assert {p.name for p in written} == {f"raw_{_TARGET}.json", "fetch_report.json"}
    raw = json.loads((tmp_path / f"raw_{_TARGET}.json").read_text(encoding="utf-8"))
    assert raw["asin"] == _TARGET
    assert raw["count"] == 11
    assert raw["fetcher_version"] == "0.1.0-offline"
    assert {"review_id", "asin", "title", "body", "rating", "review_date"} <= set(raw["reviews"][0])

    report = json.loads((tmp_path / "fetch_report.json").read_text(encoding="utf-8"))
    assert report["outcomes"][0]["captured_vs_cap"] == "13/13"
    assert report["generated_at"] == "2026-09-19T00:00:00Z"


def test_write_raw_reviews_dedupes_by_review_id(tmp_path: Path):
    reviews = [
        RawReview(review_id="R1", asin="A", title="t", body="b", rating=5, review_date="2026-01-01"),
        RawReview(review_id="R1", asin="A", title="dup", body="b2", rating=4, review_date="2026-01-02"),
        RawReview(review_id="R2", asin="A", title="t2", body="b3", rating=3, review_date="2026-01-03"),
        # review_id 缺失的**不参与**去重（无法判别是否重复，交给 clean 层 sha1 兜底）
        RawReview(review_id="", asin="A", title="x", body="b4", rating=2, review_date="2026-01-04"),
        RawReview(review_id="", asin="A", title="y", body="b5", rating=1, review_date="2026-01-05"),
    ]
    path = write_raw_reviews("A", reviews, tmp_path, fetcher_version="0.1.0")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["count"] == 4                         # R1 去重掉一条，两条空 id 保留
    assert [r["review_id"] for r in payload["reviews"]] == ["R1", "R2", "", ""]
    assert payload["reviews"][0]["title"] == "t"         # 保留首次出现


# --------------------------------------------------------------------------- #
# 窗口判据（config.within_window，抓取层与清洗层共用）
# --------------------------------------------------------------------------- #

def test_within_window_helper():
    assert config.within_window("2024-09-19", now=_NOW, months=24) is True    # 边界含
    assert config.within_window("2024-09-18", now=_NOW, months=24) is False
    assert config.within_window("2026-09-19", now=_NOW, months=24) is True
    assert config.within_window("2026-09-20", now=_NOW, months=24) is True    # 未来日期不误删
    # 缺失 / 不可解析 → 保留（宁可保留也不误删）
    assert config.within_window("", now=_NOW, months=24) is True
    assert config.within_window("not-a-date", now=_NOW, months=24) is True
    assert config.within_window("2020-01-01", now=_NOW, months=12) is False


def test_clean_and_fetch_share_the_same_window_rule():
    """抓取层与清洗层必须用**同一个**判据（同一常量、同一函数）。"""
    from tableware_radar.clean import _within_window

    assert _within_window("2024-09-18", _NOW, 24) is False
    assert _within_window("2024-09-19", _NOW, 24) is True
    assert _within_window("", _NOW, 24) is True
