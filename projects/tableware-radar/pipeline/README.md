# tableware-radar · Python 管道

离线管道：**抓取 → 清洗去重 → 两阶段 LLM 打标 → 聚合打分**，产出唯一真源
`../data/analysis.json`。数据结构/接口签名以 `../docs/ARCHITECTURE.md` 为准。

## 1. 环境准备

```powershell
# 使用团队托管的隔离 venv（Python 3.13）
$py = "C:\Users\Samuel\.workbuddy\binaries\python\envs\tableware-radar\Scripts\python.exe"

# 安装依赖
& $py -m pip install -r pipeline\requirements.txt
```

## 2. 运行测试（不依赖网络 / 不依赖真实 LLM）

```powershell
cd pipeline
& $py -m pytest
```

## 3. ★ 环境踩坑记录（探针实测固化，勿重蹈）

> 以下均为 `probe/REPORT.md` 里**实际踩到并解决**的坑，管道环境准备时按此执行。

| # | 现象 | 根因 | 处理 |
| --- | --- | --- | --- |
| 1 | `python -m scrapling install` 报 `No module named scrapling.__main__` | scrapling 无 `__main__` | 必须调用 `Scripts\scrapling.exe install` |
| 2 | `page.markdown()` 抛 `ImportError`（markdownify） | `[fetchers]` extra 不含 `markdownify` | 单独 `pip install markdownify`（已写入 requirements.txt） |
| 3 | `StealthyFetcher` 启动即崩：`Executable doesn't exist ... chromium-1234` | `scrapling install` **只装 Playwright 浏览器，不装 patchright 浏览器** | **仅兜底时**才需要 `patchright install chromium`（约 191MB+114MB） |
| 4 | `scrapling install` 首次下载卡死（只落 22 个文件、进程挂起十几分钟） | 网络中断 | 删除半成品 `chromium-1234` + `__dirlock`，重跑一次即完成（310 个文件） |

> ⚠️ **定位澄清**：`patchright` / 浏览器路径在本项目**仅作抓取失败时的兜底，非 MVP 前置**。
> 探针已证明 **L1（纯 HTTP `Fetcher`）就够用**；且浏览器路径对 Amazon 的**登录墙（政策墙，非反爬墙）无效**。
> **禁止**在任何方案或文案中写入 `solve_cloudflare`（Amazon 不使用 Cloudflare）。

## 4. 配置项（全部在 `src/tableware_radar/config.py`，可用环境变量覆盖）

| 环境变量 | 默认 | 含义 |
| --- | --- | --- |
| `TABLEWARE_ASINS` | `config/asins.txt` 或内置默认 | 逗号分隔的 ASIN 清单（**关键：不硬编码**） |
| `TABLEWARE_RESERVE_ASINS` | `config/asins.reserve.txt` 或空池 | 逗号分隔的**备选** ASIN 池（失败位换选用） |
| `TABLEWARE_TARGET_PER_ASIN` | `13` | 每 ASIN 目标条数（首屏平台上限 ~13） |
| `TABLEWARE_MIN_PER_ASIN` | `10` | 单 ASIN 成功阈值（**窗口内**条数） |
| `TABLEWARE_TIME_WINDOW_MONTHS` | `24` | 评论时间窗（月）；窗口外**不落盘** |
| `TABLEWARE_HITS_MIN` / `TABLEWARE_ASIN_RATIO` / `TABLEWARE_ASIN_FLOOR` | `3` / `0.3` / `3` | `rankable` 三阈值 |
| `TABLEWARE_MATRIX_TOP_ASINS` | `5` | ③ 对比矩阵默认列数（5–8） |
| `TABLEWARE_FETCHER` | `amazon_uk` | `amazon_uk` \| `fixture` |
| `TABLEWARE_FETCH_ATTEMPTS` / `TABLEWARE_FETCH_BACKOFF` | `3` / `2.0` | 单 ASIN 请求级重试上限 / 退避倍率 |
| `TABLEWARE_FETCH_MIN_DELAY` / `TABLEWARE_FETCH_MAX_DELAY` | `3.0` / `8.0` | 位次间限速（秒） |
| `TABLEWARE_LLM_BATCH` | `20` | LLM 批大小（15–20） |
| `TABLEWARE_OTHER_GATE` / `TABLEWARE_FAILURE_GATE` | `0.15` / `0.10` | 闸门①/② |

ASIN 清单：复制 `config/asins.example.txt` 为 `config/asins.txt` 并填入 8–10 个自选 ASIN
（选自 UK Best Sellers `plates & bowls`，评论量 ≥100、评分带 4.0–4.6，覆盖维度多样性，见 ARCHITECTURE §10-U4）。

备选池：复制 `config/asins.reserve.example.txt` 为 `config/asins.reserve.txt`。某位抓取失败或
**窗口内**条数 < 10 时，按 FIFO 换一个备选 ASIN 重试 —— **不降条数、不转半自动、不上登录态**；
池子耗尽则该位如实记为失败。留空 = 没有备选。

## 5. 目录约定

- `config/`：`dimensions.yaml`（维度唯一真源）、`asins.txt`（目标清单）、`asins.reserve.txt`（备选池）
- `data/`：中间产物与 `analysis.json`（页面唯一真源）；`data/logs/` 落 `fetch.log` / `labeling.log` / `run.log`
- `data/raw/`：`raw_<asin>.json`（逐 ASIN，按 `review_id` 幂等覆盖）+ `fetch_report.json`
  （逐位「捕获条数 vs 平台上限 13」对比，见 `../probe/README.md` §3）
- 除 `dimensions.yaml` 与 `analysis.json` 外的中间文件都是**可重跑产物**，不得被页面或插件读取

## 6. 离线可复现

测试**不联网、不调真实 LLM**：
- 抓取层：把 `ScraplingAmazonUkFetcher._get` 换成读 `../probe/artifacts/` 里的**真实商品页 HTML**
  （解析 / 拦截检测 / 报告构造全走真实代码路径，只有 HTTP 被替换）；
- 打标层：向 `DshHeadlessClient` 注入**假 runner**，批量切分 / 重试 / 修复 / 二分拆批全走真实代码路径。

## 7. 端到端运行（CLI）

```powershell
cd pipeline
$env:PYTHONPATH = "src"                       # 或先 `pip install -e .` 装成包
python -m tableware_radar.cli run --all       # 一条命令跑通全链路
```

一条命令跑通 **抓取 → 清洗 → 阶段 A → 阶段 C → 聚合**，产出 `data/analysis.json`
（页面唯一真源）。闸门破线时先落 **partial `analysis.json`**（带 `data_quality.gate`）再非零退出。

| 命令 | 作用 |
| --- | --- |
| `run --all`（默认，可省略） | 全链路 |
| `run --only fetch\|clean\|a\|c\|aggregate` | 只跑到该步（含），便于分段调试 |
| `doctor` | 环境自检（node / dsh / dimensions.yaml / ASIN 清单），**不联网** |

## 8. 关键词商品发现（基础链路已验证）

正式分析前先生成一份可人工确认的代表性商品清单；该命令不会抓评论、调用 LLM 或自动启动分析：

```powershell
cd pipeline
$env:PYTHONPATH = "src"
python -m tableware_radar.cli discover --keyword "ceramic pasta bowls" --count 10
```

默认输出 `../data/discovery/ceramic-pasta-bowls.json`，包含全部解析候选、入选标记、价格/评分/评论量、抽样分层和入选原因。抽样会排除广告、评论量不足和相关度不足的商品，并覆盖高热度、中等评分、较低价格与较高价格样本。

真实探针确认 Amazon UK 站内搜索页会返回 HTTP 202 JavaScript WAF，无头 Chromium 同样返回 503。因此当前命令使用 Yahoo 搜索结果发现 Amazon UK 的 `/dp/<ASIN>` 链接，再逐一读取 Amazon 商品详情页获得标题、价格、评分和评论量；搜索引擎数据不参与正式商品指标或后续评论分析。站内搜索墙会被明确报错，不会把空列表伪装成成功。

首个真实测试词为 `ceramic pasta bowls`。人工确认 10 个商品位后，抓取阶段对评论不足的 3 个商品自动使用备选商品替换，最终 10 个商品位全部达到每个至少 10 条评论的阈值，共保留 123 条 24 个月窗口内评论。发现清单、原始评论、清洗结果和日志都属于本地运行产物，受项目 `.gitignore` 保护，不进入统一仓库。

当前后半段仍使用 DSH Headless 调用 LLM。真实运行在暖机阶段因 API 额度不足停止，尚未生成新的动态购买诉求结果；已有评论数据可直接续跑，无需重新发现商品或抓取。下一步是先完成并验证独立 CLI 分析闭环，再把稳定命令接入工作台。

**前置检查（快速失败，PRD §8.2）**：`config/dimensions.yaml` **不存在** → 提示以
`dimensions.example.yaml` 为起点复制；**存在但 `validate()` 不过** → 拒绝执行。
两种情况都打印**可直接复制执行**的命令。任一阶段失败同样打印可复制修复命令并非零退出。
