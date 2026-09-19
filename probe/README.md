# 抓取可行性探针 —— 结论落地索引（T04 回填）

> 本文件是**结论的落地索引**，回答"探针说了什么 → 代码里怎么落的"。
> 完整证据与逐题回答见 [`REPORT.md`](./REPORT.md)；原始 HTML 在 [`artifacts/`](./artifacts/)。

---

## 0. 一句话结论

**方案 B 成立：`Fetcher`（纯 HTTP + Chrome TLS 指纹）稳定拿到商品页，无验证码、无 Cloudflare；
但单 ASIN 无登录态只有 13 条 —— 所以用「N 个 ASIN × 每 ASIN ~13 条」的广度换深度。**

| 判定项 | 结论 |
| --- | --- |
| 需要的最高抓取强度 | **L1 纯 HTTP**（`Fetcher` + `impersonate='chrome'` + `stealthy_headers=True`） |
| 商品页 HTTP | **200**，无验证码 / 无 robot check / 无 Cloudflare，连续 3 次一致 |
| 单 ASIN 条数上限 | **13**（商品页 "Top reviews" 挂件上限） |
| 翻页 | ❌ **不可行** —— 评论页 302→`/ap/signin`，分页 AJAX 端点 **401** |
| 登录墙性质 | **Amazon 产品政策墙（2024-11 起对未登录用户隐藏"全部评论"），不是反爬** |
| 隐身浏览器能否绕过 | **不能**（StealthyFetcher / DynamicFetcher 同样撞登录墙） |
| 代理 | MVP **不需要**（单出口 IP 14 次请求零拦截） |
| `variant`（颜色/尺寸） | ⚠️ **更正 REPORT 的「0/13」**：商品页 review 节点带 `[data-hook="format-strip"]`，T04 实测 **13/13 = `"Size Name: 10.5 Inch"`**。字段契约仍可空（`Optional[str]`） |
| `helpful_votes` | ⚠️ 部分（实测 7/13）—— 无票节点不存在，**缺失是常态，不是错误** |

### 明确禁止写进方案的东西

* ❌ `solve_cloudflare` —— Amazon **不使用** Cloudflare，本次全程未遇 Cloudflare 挑战。写进代码/文案都是错的。
* ❌ 浏览器路径（`StealthyFetcher` / `DynamicFetcher`）—— 商品页结果**完全相同（同样 13 条）**却慢 10–20 倍；
  对登录墙**无效**。定位 = **兜底时才需要**，非 MVP 前置。
* ❌ 翻页 / 登录态 —— 政策墙，非技术问题。

---

## 1. 落地锚点：探针结论 → 代码

| 结论 | 落地位置 |
| --- | --- |
| L1 纯 HTTP 口径（唯一抓取实现） | `pipeline/src/tableware_radar/fetch/amazon_uk.py` → `ScraplingAmazonUkFetcher`（`scrapling` **惰性 import**） |
| 商品页 DOM 适配（`<h5>` 标题、`data-hook="reviewText"` 正文） | 同文件「纯解析层」：`parse_review_element` |
| 正文 UI 噪声（`Brief content visible…` / `Read more` / `Read less`） | 同文件 `clean_body_noise`（解析层与 `clean.py` 共用） |
| 单 ASIN 平台上限 = 13 | `config.PLATFORM_CAP_PER_ASIN`（写进 `FetchReport.platform_cap`） |
| 单 ASIN 成功线 = 10 | `config.MIN_REVIEWS_PER_ASIN` |
| 重试 / 指数退避 | 同文件 `AmazonUkRun._attempt` / `_backoff`（`config.FETCH_MAX_ATTEMPTS`、`FETCH_BACKOFF_FACTOR`） |
| 验证码 / 登录墙**不重试** | 同文件 `is_hard_stop()` + `HARD_STOP_PREFIXES` |
| 失败 / 不足 10 条 → **换 ASIN**（不降条数） | 同文件 `AmazonUkRun._fetch_slot` |
| 24 个月窗口**不落盘** | `config.within_window()`（抓取层与 `clean.py` 共用同一判据） |
| 限速：ASIN 之间 3–8s | `config.FETCH_MIN_DELAY_S` / `FETCH_MAX_DELAY_S`（`_sleep_between_slots`） |
| 报告「捕获条数 vs 平台上限」 | `data/raw/fetch_report.json` → `outcomes[].captured_vs_cap`，如 `"13/13"` |
| 采样偏差（精选 Top reviews 非随机） | `aggregate.py` 的 `data_quality.sampling_bias`；页面 ⑧ 区块展示 |

抓取器选择开关：`config.FETCHER_NAME`（`amazon_uk` | `fixture`），工厂在 `fetch/__init__.py`。

---

## 2. 方案 B 的数据模型（用户已拍板 v1.3，勿再变更）

```
目标位（slot）= 8–10 个自选 ASIN
每 ASIN      ≈ 13 条（首屏口径，无登录态）
合计         ≈ 104–130 条原始评论
```

* 某位**失败或不足 10 条** → 从 **备选池 FIFO 换一个 ASIN 重试**（记 `swapped_from`）。
* **不降条数、不转半自动、不上登录态**。备选池耗尽就如实记为失败。
* 备选池来源：`TABLEWARE_RESERVE_ASINS` 环境变量 → `config/asins.reserve.txt`（默认空池）。

### 为什么不是「3 ASIN × 100 条」

那需要登录态：账号风控、cookie 维护、合规风险，且**是政策墙不是技术墙**，投入大而脆弱。
而 `rankable = hits≥3 且 asin_count≥max(3, ceil(0.3×asins_with_data))` 需要的正是**跨商品复现**，
广度比深度更契合"品类共性"这一业务目标。

---

## 3. `fetch_report.json` 形状（节选）

```jsonc
{
  "platform_cap_per_asin": 13,
  "min_reviews_per_asin": 10,
  "time_window_months": 24,
  "reserves_used": ["B0ZZZZZZZZ"],
  "outcomes": [
    {
      "slot": 0,
      "asin": "B0157FD9MS",
      "requested_asin": "B0157FD9MS",
      "swapped_from": null,
      "status": "captured",              // captured | swapped | failed
      "ok": true,
      "requested": 100,
      "captured": 13,                    // 捕获条数（含窗口外）
      "in_window": 11,                   // ★ 真正落盘的条数
      "dropped_out_of_window": 2,
      "platform_cap": 13,
      "captured_vs_cap": "13/13",        // ★「是否抓全」一眼可读
      "attempts": 1,
      "error": ""
    }
  ],
  "summary": {
    "slots": 1, "captured_slots": 1, "swapped_slots": 0, "failed_slots": 0,
    "full_capture_slots": 1, "captured_total": 13, "in_window_total": 11,
    "dropped_out_of_window_total": 2, "attempts_total": 1
  }
}
```

> `captured` 与 `in_window` **必须分列**：前者回答"抓全了吗"（对比平台上限 13），
> 后者回答"有多少能用"（窗口过滤后、真正落盘并进入聚合分母的条数）。

---

## 4. 环境陷阱（复现必读）

1. **`scrapling install` 只装 Playwright 浏览器，不装 StealthyFetcher 需要的 patchright 浏览器。**
   需额外 `patchright install chromium`（约 191MB + 114MB），否则 `StealthyFetcher` 启动即崩
   （`Executable doesn't exist ... chromium-1234`）。**但本项目默认不用浏览器**，所以这只在"兜底"时才是前置。
2. `python -m scrapling install` **无效**（无 `__main__`），必须 `Scripts\scrapling.exe install`。
3. `scrapling install` 首次可能**下载卡死**；删掉半成品**重跑一次即完成**（310 个文件）。
4. `page.markdown()` 依赖 **`markdownify`**，而 `[fetchers]` extra **不含它** —— 需单独装。
5. 实测可用版本 **`scrapling 0.4.15`**（`pipeline/requirements.txt` 的版本约束以实测为准）。
6. 本仓库**不引入** `pandas`、任何 LLM SDK（LLM 走 `dsh` 子进程）。

---

## 5. 证据文件

| 文件 | 说明 |
| --- | --- |
| `artifacts/L1_http_product_B0157FD9MS.html` | **商品页真产物**（1.9MB，13 条评论）—— T04 离线单测的夹具 |
| `artifacts/L1_http_reviews_p1_B0157FD9MS.html` | 独立评论页（**实为 signin 页**）—— 登录墙证据 |
| `artifacts/L1_http_mobile_dp_B0157FD9MS.html` | 移动端路径（同样 13 条，无增益） |
| `artifacts/L2_stealth_product_B0157FD9MS.html` | 隐身浏览器商品页（同样 13 条 ⇒ 无必要） |
| `artifacts/L3_stealth_reviews_p1_*` / `L4_dynamic_reviews_p1_*` | 隐私身/动态均 302→signin ⇒ 绕不过 |
| `artifacts/MD_http_product_markdown_B0157FD9MS.md` | `page.markdown()` 产物 |
| `artifacts/steps.jsonl` | 每步结构化结果（含字段覆盖统计与报错原文） |
| `probe_amazon_uk.py` | 探针主脚本（成功的 L1 配置即流水线抓取层） |
| `inspect_artifact.py` / `inspect_markup.py` / `dump_review_block.py` / `debug_id.py` | 离线分析工具（**不发请求**） |

---

## 6. 离线可复现

T04 的测试**完全不联网**：把 `ScraplingAmazonUkFetcher._get` 换成读
`artifacts/L1_http_product_B0157FD9MS.html`，因此**解析、拦截检测、报告构造全走真实代码路径**，
只有 HTTP 被替换。见 `pipeline/tests/test_fetch_amazon_uk.py`。

```bash
cd pipeline
python -m pytest tests/test_fetch_amazon_uk.py -q      # 19 passed
```

该真产物在固定"现在" = `2026-09-19` 下的窗口表现：**捕获 13 → 窗口内 11 → 丢弃 2**
（`R1VU6P949QZXXI` 2024-04-17、`R1W4JZG6ESAVMR` 2024-02-08），正好覆盖"窗口外不落盘"。
