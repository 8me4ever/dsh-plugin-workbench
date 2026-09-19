# Amazon UK 餐盘碗碟评论抓取 —— 可行性探针报告（Spike）

> 项目：`dsh-tableware-radar`　|　任务：抓取可行性探针（反爬验证）
> 执行：工程师 寇豆码（Kou）　|　日期：2026-09-19
> 探针脚本：`probe/probe_amazon_uk.py`　|　原始证据：`probe/artifacts/`

---

## 0. 结论（先行）

**判定：部分可行（技术上「能抓」，但「抓够 60 条/ASIN」在无登录态下不可行）。**

- ✅ **不需要任何隐身浏览器**：最低强度的 `Fetcher + impersonate='chrome'`（纯 HTTP + TLS 指纹伪装）即可稳定拿到商品页，**HTTP 200、无验证码、无 robot check**，重复 3 次结果一致。
- ✅ 可稳定提取的字段：`review_id / rating / title / body / review_date / country / verified_purchase / helpful_votes(部分)`。
- ❌ **关键数字：单个 ASIN 无登录态只能拿到 13 条评论**（商品页 "Top reviews" 挂件上限），**达不到 PRD 的 ≥60 条/ASIN 验收线**。要拿更多必须登录。
- ❌ **登录墙是硬的、且与反爬无关**：独立评论页 `/product-reviews/<ASIN>/` 对**所有** fetcher 都 302 跳转 `/ap/signin`；评论分页 AJAX 端点直接返回 **401**。隐身浏览器（StealthyFetcher）**不能**绕过它——这不是 bot 检测，是 Amazon 自 2024-11 起对未登录用户关闭"全部评论"。
- ➡️ **给项目的最重要建议**：把 MVP 的数据结构从「3 ASIN × 100 条」改为「**更多 ASIN（15–30 个）× 每 ASIN ~13 条**」，用广度换深度。既规避登录墙，又更契合"品类共性"这一业务目标。

---

## 1. 环境与依赖（可复现）

| 项 | 值 |
| --- | --- |
| Python | 3.13.14（隔离 venv：`C:\Users\Samuel\.workbuddy\binaries\python\envs\tableware-radar`） |
| scrapling | **0.4.15** |
| 关键依赖 | `curl_cffi`(TLS 指纹)、`patchright`(StealthyFetcher 内核)、`playwright`(DynamicFetcher 内核)、`markdownify`(`markdown()` 依赖) |
| 浏览器内核 | Playwright `chromium-1243`；Patchright `chromium-1234` |

**踩坑记录（流水线需固化）：**

1. **`scrapling install` 只装 Playwright 的浏览器，不装 StealthyFetcher 需要的 patchright 浏览器。** 必须额外跑一次 `patchright install chromium`（约 191MB + 114MB），否则 `StealthyFetcher` 启动即崩（`Executable doesn't exist ... chromium-1234`）。**这是流水线的必做前置步骤。**
2. `scrapling install` 首次可能**下载卡死**（只落 22 个文件、进程挂起十几分钟）；删除半成品后**重跑一次即完成**（310 个文件）。流水线里应加"装完校验文件数/可执行文件存在"的健壮性检查。
3. `python -m scrapling install` **无效**（无 `__main__`），必须调用 `Scripts\scrapling.exe install`。
4. **`page.markdown()` 需要 `markdownify`，而 `[fetchers]` extra 不含它**——需 `pip install markdownify`（或装 `scrapling[rag]`）。
5. **关于 StealthyFetcher 的认知纠正**：0.4.15 的 `StealthyFetcher` 内核是 **patchright（Playwright 的 stealth 分支）**，**不是 Camoufox**（旧版本才用 Camoufox）。且 `solve_cloudflare` 对本任务无意义（Amazon 不用 Cloudflare）——本次探针全程**未遇到任何 Cloudflare 挑战**，与 PRD 8.3 判断一致。

---

## 2. 目标 ASIN 的选取

| 项 | 值 |
| --- | --- |
| **ASIN** | `B0157FD9MS` |
| 商品 | **Amazon Basics 6-Piece White Dinner Plate Set, 10.5 inches** |
| 商品页 | `https://www.amazon.co.uk/dp/B0157FD9MS` |
| 评分/评论数 | 4.6 / **12,597 条**（页内实测） |
| 选取理由 | 它在第三方 UK 选品数据源（flank.com 的 *Amazon UK "Plates"* 页）被列为该类目 **Top 1 在售爆品**，带 UK 定价（£11.68），且评论基数极大——**只有评论够多，才能真实检验"翻页能否拿到 60+"**。 |

> 实测确认该 ASIN 在 amazon.co.uk 真实在售（HTTP 200、`#productTitle` 命中、386 处 ASIN 引用、评论作者国家均为 United Kingdom）。

---

## 3. 逐级抓取强度结果（核心证据）

| 级别 | fetcher / 参数 | 目标 URL | HTTP | 验证码/robot | 解析评论数 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| **L1** | `Fetcher.get(impersonate='chrome', stealthy_headers=True)` | `/dp/B0157FD9MS` | **200** | 无 | **13** | ✅ 可行 |
| L1 | 同上（移动端路径） | `/gp/aw/d/B0157FD9MS` | 200 | 无 | 13 | 同桌面，无增益 |
| L1 | 同上 | `/product-reviews/B0157FD9MS/` | 200（**实为 signin 页**） | 登录墙 | **0** | ❌ 需登录 |
| L1 | `session.post` | `/hz/reviews-render/ajax/reviews/get/` | **401** | — | 0 | ❌ 需登录 |
| **L2** | `StealthyFetcher.fetch(headless, network_idle, locale='en-GB')` | `/dp/B0157FD9MS` | 200 | 无 | **13** | ✅ 可行但**无增益** |
| L2/L3 | `StealthyFetcher` | `/product-reviews/B0157FD9MS/` | **302→200(signin)** | 登录墙 | 0 | ❌ 隐身**无法**绕过 |
| **L4** | `DynamicFetcher.fetch(headless, network_idle)` | `/product-reviews/B0157FD9MS/` | 302→200(signin) | 登录墙 | 0 | ❌ 同上 |
| **稳定性** | `Fetcher`（HTTP）商品页 **×3** | `/dp/B0157FD9MS` | 200/200/200 | 无 | 13/13/13 | ✅ 高度稳定 |
| **markdown** | `Fetcher` + `page.markdown()` | `/dp/B0157FD9MS` | 200 | 无 | — | ✅ 正常 |

**原始证据文件**（`probe/artifacts/`）：

- `L1_http_product_B0157FD9MS.html`（1.9MB，商品页，无拦截）
- `L1_http_reviews_p1_B0157FD9MS.html`（117KB，**实为 signin 页**）
- `L1_http_mobile_dp_B0157FD9MS.html`（2MB）
- `L2_stealth_product_B0157FD9MS.html`（2.3MB）
- `L3_stealth_reviews_p1_B0157FD9MS.html` / `L4_dynamic_reviews_p1_B0157FD9MS.html`（均为 signin 页）
- `MD_http_product_markdown_B0157FD9MS.md`（markdown 产物，113KB）
- `steps.jsonl`（每一步的结构化结果，含字段覆盖统计与报错原文）

登录墙证据（来自 signin 页跳转 URL，脱敏保留）：

```
GET /product-reviews/B0157FD9MS/            -> 302
GET /ap/signin?openid.return_to=...
      %2Fproduct-reviews%2FB0157FD9MS%2F... -> 200  (登录页)
POST /hz/reviews-render/ajax/reviews/get/   -> 401 Unauthorized
```

---

## 4. 必答问题逐条回答

### Q1. 哪一级抓取强度可行？具体参数？
**最低的 L1 级就够——不需要浏览器。**
```python
from scrapling.fetchers import Fetcher
page = Fetcher.get("https://www.amazon.co.uk/dp/<ASIN>",
                   impersonate="chrome", stealthy_headers=True, timeout=30)
```
- 纯 HTTP + curl_cffi 的 Chrome TLS 指纹即可通过商品页，**无验证码、无 robot check、无 Cloudflare**。
- StealthyFetcher / DynamicFetcher 在商品页上**结果完全相同（同样 13 条）**，纯属浪费（慢 10–20 倍）。
- ⇒ **流水线应默认用 `Fetcher`（HTTP）**；浏览器仅作兜底。

### Q2. 一个 ASIN 能拿到多少条评论？够不够？翻页呢？
- **无登录态：稳定 13 条**（商品页 "Top reviews from the United Kingdom" 挂件上限）。
- **PRD 验收线 ≥60/ASIN、目标 100：达不到。** 差距 ≈ 4.6 倍。
- **翻页不可行**：独立评论页（翻页入口）对未登录用户 302 跳登录；分页 AJAX 端点返回 401。**第 1 页就被拦在登录墙外，根本到不了第 2 页。**
- 移动端（`/gp/aw/d/`）也没有更多，同样 13 条。

### Q3. 能提取哪些字段？（对照清单）

| 字段 | 是否可提取 | 说明 |
| --- | --- | --- |
| `rating` (1–5) | ✅ 13/13 | 来自 `[data-hook="review-star-rating"] .a-icon-alt` |
| `title` | ✅ 13/13 | 商品页标题在 `<h5>`（非 `data-hook="review-title"`），需专门适配 |
| `body` | ✅ 13/13 | 商品页 hook 是 `data-hook="reviewText"`（评论页才是 `review-body`）；**含 "Brief content visible / Read more Read less" 等 UI 噪声，需清洗** |
| `review_date` | ✅ 13/13 | `"Reviewed in the United Kingdom on 4 June 2025"`，可解析日期+国家 |
| `helpful_votes` | ⚠️ 部分 7/13 | 无票数的评论该节点不存在，属正常 |
| `verified_purchase` | ✅ 13/13 | `[data-hook="avp-badge"]` |
| `country` | ✅ 13/13 | 从 date 文案解析（本商品全为 United Kingdom） |
| `review_id` | ✅ 13/13 | 商品页取 `data-reviewid`；评论页取容器 `id` |
| **`variant`（颜色/尺寸/套装）** | ✅ **13/13** | **⚠️ 订正（T04 时发现）**：商品页 review 节点带 `[data-hook="format-strip"]`，本样本全为 `"Size Name: 10.5 Inch"`。**本报告原先写的「0/13」是误读自己的 artifact**——同目录 `L1_http_product_B0157FD9MS.html` 里 `format-strip` 实测出现 13 次、`Size Name` 18 次，数据一直都在。字段仍按可空处理（并非所有 listing 都带该 strip）。 |

### Q4. 是否需要登录态？
**需要——这是本案最重要的结论。**
- 只要能拿到 **> 13 条**（即翻页/看全部评论），就**必须**携带已登录 Amazon 的 Cookie/Session。这不是绕过反爬的问题，而是 Amazon 的产品策略（2024-11 起对未登录用户隐藏"全部评论"）。
- 影响：需要 1 个真实 Amazon 账号（建议英国站）、cookie 定期维护、账号有被风控封禁的风险，且请求频率受限。
- 判断：把"登录态"引入 MVP **显著增加复杂度和合规/账号风险**，应先确认是否值得。

### Q5. `page.markdown()` 是否正常？质量如何？
**正常工作。** 产物 `MD_http_product_markdown_B0157FD9MS.md`：
- 113KB / 848 非空行；"极短行"占比仅 **1.5%**（噪声低）；**评论正文完整保留**（含 `N out of 5 stars` 18 处、`Brief content visible...` 评论体）。
- **残留噪声集中在页面顶部**：导航菜单、全量品类下拉列表（"All DepartmentsAlexa Skills…"）、键盘快捷键提示、`Hello, sign in` 等。
- 建议：喂 LLM 前用 `page.markdown(main_content_only=True)` 或 `page.markdown(css_selector="#customerReviews, #feature-bullets")` 做区域裁剪，即可去掉绝大部分导航噪声。

### Q6. 稳定性判断？
- HTTP 路径商品页 **连续 3 次 200、无拦截、评论数恒为 13**，`html_len` 波动 <1%。**高度稳定，无偶发拦截。**
- 4 次独立商品页请求（含浏览器路径）**均未触发验证码**。当前该出口 IP 未被 Amazon 风控。

### Q7. 给流水线的抓取策略建议
1. **抓取层用 `Fetcher`（HTTP）而不是浏览器**：够用、快、稳、省资源。浏览器仅作失败兜底。
2. **限速**：本次 4–5s 间隔、14 次请求零拦截。建议正式流水线 **同一域名 1 请求 / 5–10s 起步**，并监听 503 / robot check，命中即翻倍退避。
3. **复用 session**：用 `FetcherSession(impersonate='chrome')` 复用 cookie/TLS 连接，降低特征暴露。
4. **代理**：本次单出口 IP 未触发风控，**MVP 阶段无需代理**；若上量（P2 的 Top20）再引入。
5. **兜底路径**：如遇 403/503，再降级 `StealthyFetcher`（记得先 `patchright install chromium`）。
6. **数据量策略（关键）**：正视"**每 ASIN 上限 ~13 条**"，改用 **广度换深度**——抓更多 ASIN（15–30 个同类爆品），每 ASIN 取 ~13 条，合计 200–400 条，足以支撑 `hits(d)≥3` 的维度统计。
7. **采样偏差提醒**：商品页给的是 **"最有用/精选 Top reviews"**，不是随机样本。它偏向高票/长评，做"好评/差评集中在哪"可用，但**不代表全体分布**，报告中须标注。
8. **数据清洗**：body 里的 `Brief content visible... Read more Read less` 必须正则剔除（已有实现可参考 `probe_amazon_uk.py`）。

---

## 5. 请求预算

**总请求数：14 次**（≤ 15 上限）。明细（均记录在 `artifacts/steps.jsonl`）：

| # | 请求 | 次数 |
| --- | --- | --- |
| 1 | 商品页 GET（HTTP `Fetcher`，首测） | 1 |
| 2 | 独立评论页 GET（→ signin） | 1 |
| 3 | 移动端商品页 GET | 1 |
| 4 | 分页 AJAX 尝试 v1（GET 商品页取 token + POST medley 端点） | 2 |
| 5 | markdown 测试（GET 商品页） | 1 |
| 6 | 分页 AJAX 尝试 v2（GET 商品页 + POST `reviews/get` 端点→401） | 2 |
| 7 | 浏览器评论页 GET（DynamicFetcher → signin） | 1 |
| 8 | 稳定性验证（GET 商品页 ×3） | 3 |
| 9 | 浏览器商品页 GET（StealthyFetcher） | 1 |
| 10 | 浏览器评论页 GET（StealthyFetcher → signin） | 1 |
| | **合计** | **14** |

无任何为"多拿数据"的重复重试。


---

## 6. 诚实声明与局限

- 本报告所有数字均来自 `probe/artifacts/` 的真实抓取产物，**未使用任何样例/编造数据**。
- 探针只测了 **1 个 ASIN**。虽然特性（登录墙）是 Amazon 全站行为、且多来源佐证（Unwrangle、Apify 均确认 2024-11 后的登录限制），但不同 ASIN 商品页挂件条数可能有 8–13 的浮动，未逐一验证。
- 未测试**登录态**路径（无账号，且涉及合规/账号风险，需先经 PM/用户决策）。
- 未测**代理**路径（本次单 IP 未被封，无必要）。
- `L1_medley_ajax_B0157FD9MS.txt` 为 0 字节，因第二次（正确端点）返回 401 空响应覆盖了第一次（404）的内容；两次状态码均如实记录在 `steps.jsonl`。

---

## 7. 交付物

| 文件 | 说明 |
| --- | --- |
| `probe/probe_amazon_uk.py` | 探针主脚本（逐级 fetcher，可按 `--step` 复跑；成功的 L1 配置即流水线抓取层） |
| `probe/inspect_artifact.py` | 离线解析已存 HTML，输出商品身份/字段覆盖（不发请求） |
| `probe/inspect_markup.py` | 离线分析评论 DOM 结构 / AJAX 端点 |
| `probe/dump_review_block.py` | 离线 dump 单个评论块，用于修正选择器 |
| `probe/debug_id.py` | 离线调试 review_id 抽取 |
| `probe/artifacts/*` | 各级原始 HTML / markdown / `steps.jsonl` 证据 |
| `probe/REPORT.md` | 本报告 |
