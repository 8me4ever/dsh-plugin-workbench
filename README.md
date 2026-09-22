# dsh-plugin-workbench

> **统一仓库**：Job Radar 与 Tableware Radar 已完整迁入 `projects/`，本包是
> 唯一需要维护、同步和安装的 DSH 插件。仓库结构、数据边界和换机步骤见
> [`docs/UNIFIED-REPOSITORY.md`](docs/UNIFIED-REPOSITORY.md)。

DSH 的可视化工作台。侧栏底部一个入口，点一下 —— **右侧主区域整个变成工作台**：首页是一张暗色、结论优先的个人指挥台，详情页承载完整业务操作。

项目 01 **Job Radar** 与项目 02 **出海业务用户调研**均已接入。两个内部预留项目位不在首页制造占位噪声，后续新增项目时仍可沿用扩展契约。

## 当前状态

- **统一仓库已完成**：工作台、两个业务项目及精选结果统一维护；旧业务仓库只保留归档历史。
- **暗色首页已落地**：首页直接呈现最匹配岗位、选品结论、核心维度与关键因素，不展示低价值过程指标。
- **同步中心已完成第二阶段**：除分支和远端差异预览外，现可选择安全文件、核对 diff，并在二次确认后创建本地提交；拉取、推送、安装和重启仍未接入。
- **出海调研基础链路已跑通前半段**：输入英文细分品类关键词后，可发现 Amazon UK 候选商品、按热度/评分/价格分层选出 8–10 个代表样本，并在人工确认后抓取和清洗评论。首个测试词 `ceramic pasta bowls` 已获得 10 个有效商品位和 123 条窗口内评论。
- **动态购买诉求分析尚未完成**：评论数据已保存在本地且不会上传 Git；现有 DSH Headless LLM 因 API 额度不足无法继续。下一阶段将先把独立本地管道跑通并验证，再接入工作台，不在额度问题解决前改造页面。
- **详情能力保持完整**：岗位筛选与状态写回、品类对比矩阵及完整分析仍在各项目详情页中提供。

> **版本要求：dsh >= 0.1.5-rc.2。** 工作台占的是 layout 的 `main` 插槽、靠 `ctx.layout.selectPanel()` 切换，
> 这两个东西都是 0.1.5 的 layout 才有的。0.1.1 的 `LayoutController` 只有
> `attachPanels/toggleSidebar/openDetails/closeDetails`，中间那一列被硬接在 `conversation` 插槽上，
> 根本没有"面板"这个概念可以选进去。在旧 host 上，侧栏入口挂得上但点了没反应（`apply()` 里对
> `main` 的注册是 try/catch 包着的，不会带崩整个插件）。

---

## 它长什么样

```
┌─ 侧栏底部 ─────────────┐
│  ⚙ 设置                │
│  ▤ 工作台   ← 入口      │   ← sidebar.footer.action
└────────────────────────┘
        ↓ 点击：不是弹窗，是主区域整体换成工作台
┌──────────────────────────────────────────────────────────┐
│ ← →  工作台 / 项目 01                     [ 返回会话 ]     │  ← main 插槽的 chrome
├──────────────────────────────────────────────────────────┤
│  系统状态 / 业务项目 / 代码同步              [刷新数据]  │
│                                                          │
│  ┌──────────────────────┐ ┌──────────────────────────┐  │
│  │ Job Radar            │ │ 出海业务用户调研          │  │
│  │ 最匹配的 5 个岗位     │ │ 选品结论、核心维度与因素   │  │
│  │ 匹配原因与处理状态    │ │ 不展示低价值过程指标       │  │
│  └──────────────────────┘ └──────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 同步中心 · 分支 / 待上传 / 待下载 / 本地改动       │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
        ↓ 点项目操作
┌──────────────────────────────────────────────────────────┐
│ ← →  工作台 / 项目 01                     [ 返回会话 ]     │
├──────────────────────────────────────────────────────────┤
│  Job Radar 那一屏                                        │   ← 子项目页
└──────────────────────────────────────────────────────────┘
```

**左上角是浏览器式的前进/后退**（也支持 `Alt + ←` / `Alt + →`）。点项目操作 = 进入详情页，后退 = 回首页。
`返回会话` 把主区域还给对话（等价于 `selectPanel(null)`）。

宿主插件清单仍保留为诊断页，但正常时不占首页空间；只有读取或启动异常才进入全局状态提醒。

侧栏入口在**有插件启动失败**时会带上红色数字角标。

---

## 项目 01：Job Radar

`src/client/projects/jobRadar.ts` —— 它同时是"接一个项目"的**完整样板**，不只是个占位。

它展示三件你在第二个项目里会重复遇到的事：

**1. 数据从哪来 —— 由统一宿主 Remote 读写。**
岗位数据由本插件宿主半部通过 `remote.jobRadar` 提供，状态标记也沿同一条 Remote 写回统一仓库里的 `jobs.json`，不存在第二份快照。

**2. 异步挂载要当暂态处理。**
`remote.jobRadar` 与 UI 同包交付，但客户端数据面仍可能晚于页面挂载。因此它没有写进 `inject`，而是在每次读取时通过 `ctx.reflect.get('remote.jobRadar')` 现场解析；暂时解析不到就渲染说明卡，而不是带崩工作台。

只需在统一仓库根目录安装一次：

```bash
npm run dev -- --profile web
```

**3. 拿到的不是友好对象，要在适配层里抹平。**
`remote.jobRadar` 给的是**网关原样**：每次调用返回 `{ ok, value }` 信封，而且实参个数会被按描述符声明的 `parameters.length` 严格校验。项目契约里承诺的却是直接的 `{ jobs, total }` 和可选的 filter。这一层翻译在 `src/client/projects/jobRadarRemote.ts`（`toJobRadarFace`），有两个地方不能省：

- **拆信封**。不拆的话 `res.jobs` 恒为 `undefined` —— 列表会「成功地」渲染成空，且 `ok` 一切正常，最难查。
- **补实参**。`jobRadar/list` 声明了 1 个参数，`list()` 不带参数会被直接拒掉：
  `client api: jobRadar/list expected 1 argument(s), got 0`。项目侧把 filter 写成可选是合理的，`?? {}` 由适配层补。

**4. 状态放在项目组件里，不进共享 store。**
这份数据只有这一屏要看，切换导航时重新挂载、重新读一次快照正是想要的行为。控制室/入口那种"多处都要读"的才需要共享 store。

> 两个业务 Remote 现在都由根插件的 `src/index.ts` 挂载；`projects/` 下旧插件目录仅保留迁移来源与历史，不再单独安装。

---

## 接入一个自定义项目

项目路由仍由 **`src/client/projects/slots.ts`** 管理，数组顺序就是详情页的项目顺序。首页不再自动把所有 slot 画成入口卡片；新增项目时还要在 `ControlRoom.ts` 中为它设计一个有真实摘要数据的组件，避免退回“空卡片导航页”。

接口契约在 `src/client/projects/types.ts`，最小实现只有三个字段：

```ts
// src/client/projects/myProject.ts
import { createElement as h } from 'react'
import type { WorkbenchProject } from './types.ts'

export const myProject: WorkbenchProject = {
  id: 'my-project',                    // 唯一 id，也是导航 key
  title: () => '我的项目',              // 导航与页头标题
  summary: () => '一句话说明',          // 可选，详情与扩展信息
  render: (ctx) => h('div', null, `宿主共装载 ${ctx.inventory.get().entries.length} 个插件`),
}
```

然后在 `slots.ts` 里替换掉对应的 `null`，并为首页补上对应业务摘要：

```ts
import { myProject } from './myProject.ts'

export const PROJECT_SLOTS: readonly ProjectSlot[] = [jobRadarProject, myProject, null, null]
```

跑 `node scripts/dev.mjs`，重启 host，刷新页面即可。

> 只改 `slots.ts` 已足够验证详情页路由；要让项目出现在首页，还需要在 `ControlRoom.ts` 中明确它最值得展示的结论与轻操作。

**`render(ctx)` 里不能用 hook。** 它由工作台直接调用（外面套了 try/catch，所以一个项目抛异常不会带崩别人），不是 React 组件。要有状态就按 `jobRadar.ts` 的样子把上下文交给一个真组件：`render: (ctx) => h(MyView, { ctx })`。

### 你拿到的上下文

`render(ctx)` 的 `ctx` 当前提供：

| 字段 | 是什么 |
| --- | --- |
| `ctx.t(key)` | 绑定到本插件词条的翻译函数，词条在 `src/client/index.ts` 的 `DICT_ZH` / `DICT_EN` |
| `ctx.inventory` | 宿主插件清单的只读快照（`get()` / `subscribe()`），附 `refresh()` |
| `ctx.jobRadar()` | 解析可选的数据面 `remote.jobRadar`，未装载时返回 `undefined`。**每次调用都重新解析** |
| `ctx.tablewareRadar()` | 解析 `remote.tablewareRadar`，读取统一仓库中的 `analysis.json` 精选结果 |

工作台已经给内容区加了**内边距和纵向滚动**，你的 `render` 只需要返回这一屏的内容。

需要更多宿主能力（其它 Remote、文件、网络）时，两条路都行：

- 消费一个**已经存在**的 Remote → 照 `jobRadar.ts` 抄，在 `ProjectContext` 里加一个解析函数，`client/index.ts` 的 `apply()` 里接上。
- 没有现成 Remote → 去 `src/index.ts` 给宿主半部加 `@Remote` 方法，再从项目里解析 `remote.<namespace>`。

`render` 抛异常会被工作台接住并显示成一张错误卡片，不会带崩其它项目。

---

## 上手（换一台机器）

**仓库根就是插件本体**，克隆下来直接装即可。

```bash
git clone https://github.com/8me4ever/dsh-plugin-workbench.git
cd dsh-plugin-workbench
npm i -D esbuild                 # 构建依赖；build.mjs 也会去全局/npx 缓存里找，但不保证有

npm i -g @deepseek-ai/dsh@latest # host，必须 >= 0.1.5-rc.2
node scripts/dev.mjs             # build + 冒烟测试 + 装进 web profile + 校验副本已更新
dsh web --profile web            # 重启 host，然后刷新浏览器标签页
```

`lib/` 和 `client/` 是**提交进仓库的构建产物**，所以即使不装 esbuild，也能直接 `dsh plugin add` 装上一份能跑的版本；只有要改代码才需要它。

两个业务项目的代码与精选结果都已并入本仓库，根插件会直接挂载 `remote.jobRadar` 与 `remote.tablewareRadar`，不需要再安装旧业务插件。大量原始抓取数据、缓存、日志、密钥和浏览器状态仍保留在本机，不进入 Git。

`scripts/browser-check.py` 需要 Python + Playwright（`pip install playwright && playwright install chromium`），且 host 正在 3080 上跑。

> 本 README 后面提到的 `~/.dsh/restart-dsh-web.ps1` 是原开发机上现成的辅助脚本，**不在本仓库里**；新机器上用 `dsh web --profile web` 起服务就够了。

---

## 开发循环

```bash
node scripts/dev.mjs              # build + 冒烟测试 + 装进 web profile + 校验副本已更新
node scripts/dev.mjs --profile X  # 换一个 profile
node scripts/dev.mjs --skip-smoke # 跳过冒烟测试
node build.mjs                    # 只构建
node scripts/smoke-client.mjs     # 只跑冒烟测试
python scripts/browser-check.py --no-mutate --url "<DSH 启动日志中的完整 URL>"  # 只读检查
python scripts/browser-check.py --jobs projects/job-hunting/code/job-radar/data/jobs.json --url "<完整 URL>"  # 含写入测试
```

**为什么必须重装、不能只 build。** `file:` 依赖被 pnpm **按 `files` 白名单打包复制**进 profile（`~/.dsh/profiles/web/node_modules/dsh-plugin-workbench/`），不是软链。所以改完源码只 build，profile 里还是上一份拷贝 —— 页面当然没变化。

**而且只"重新 add"也不够。** 当依赖 spec 没变化时，pnpm 会认为「Already up to date」并**跳过重新打包**，profile 里那份旧拷贝照旧留着 —— 你会以为重装了，其实没有。所以 `dev.mjs` 在 install 之后会拿 profile 里的 `client/client.js` 和刚构建的产物**逐字节比对**：不一致就自动 `remove` + `add` 强制重装，重装完再验一次；如果两次都没对齐，脚本会以非零码退出并打印手工恢复命令，而不是让你对着一个不生效的页面猜。

装完之后要重启 host（`dsh web --profile web`）并刷新浏览器标签页。本机现成的重启脚本是 `~/.dsh/restart-dsh-web.ps1`（它会停掉 3080 上的旧进程、用全局 dsh 起一个新的，并把 PID 与启动日志尾部写进 `~/.dsh/logs/restart-marker.txt`）。

### 冒烟测试能测到什么

`scripts/smoke-client.mjs` 不需要浏览器：它按模块加载器的方式加载 `client/client.js`，用一个迷你 hook 运行时把各个视图组件渲染成元素树再断言。覆盖：

- 两个插槽的注册名/id/key、侧栏宽窄两种形态、失败角标
- **注册的是 `main` 而不是 `shell.overlay`**，且侧栏入口的 id === `main` 的 key
- **点入口确实调了 `selectPanel(PANEL_ID)`**
- 面板 chrome：前进/后退初始禁用、面包屑、`返回会话`
- **前进/后退/`Alt+←`/`Alt+→` 的栈与游标语义**（含"从历史往回走后再点新卡片会截断分叉"）
- **越界 view id 被修回控制台**
- 暗色首页只暴露两个真实项目与同步中心，不显示空项目位或正常状态下的宿主诊断入口
- 首页的系统状态、真实业务摘要、读取失败和空数据状态
- 宿主插件清单页
- 项目位渲染的空 / 已接入 / 抛异常状态
- **「填入一个项目后确实能渲染出来」这条扩展路径**
- **项目 01 本体**：读 Remote、列出岗位、等级/状态与计数、本地筛选不重复取数、标记状态写回 Remote、写入被拒时把原因显示出来、数据源缺席时渲染说明卡而不是抛错、读取失败时报错
- **适配层契约**：信封被拆开、`list` 每次都带满 1 个实参、`stats` 不带实参、半挂载的命名空间按「未装载」处理
- `HistoryStore` 的单元级行为

跑它不需要启动 DSH Host，也不会改动真实 `jobs.json` —— Remote 使用 stub，服务缺席分支也有独立覆盖。

### 冒烟测试**测不到**什么（所以要 browser-check）

stub 是照着我们期望的形状写的，所以它天然测不到"两个插件之间"的错配。下面三类都真的发生过，而且全都被冒烟测试放过：

| 症状 | 真因 |
| --- | --- |
| 项目显示「数据源未装载」，但插件明明在跑 | 第三方 Remote 的命名空间没被 `$mount`，浏览器里根本不存在 |
| 客户端整块 `failed to apply loader entry` | `$mount` 内部读 `callerCtx.typert`，而调用方 `inject` 里没有 `typert` |
| 项目显示「读取岗位数据失败」 | 网关按描述符校验实参个数：`expected 1 argument(s), got 0` |

这三条只在真实 host + 真实浏览器里成立，所以 `scripts/browser-check.py` 会验证首页真实岗位与核心维度、窄屏无横向溢出、宿主诊断入口正常隐藏，再进入项目 01 断言岗位行确实渲染。可选写入测试会先备份 `jobs.json`、结束时还原。

写入那一步只在给了 `--jobs`（或 `$JOB_RADAR_JOBS`）时才跑；默认使用 `--no-mutate` 做只读检查。DSH Host 启用临时认证时，应把启动日志打印的完整本机 URL 通过 `--url` 传入，工具不会自行读取认证信息。

---

## 目录结构

```
src/
├── index.ts                      统一宿主：Job Radar、Tableware Radar、同步状态 Remote
└── client/
    ├── index.ts                  入口：建上下文、注册两个插槽、词条、测试钩子
    ├── Workbench.ts              主区域面板：chrome（前进/后退/面包屑/返回会话）+ 视图路由
    ├── ControlRoom.ts            暮光任务舱首页：业务摘要、系统状态、同步状态
    ├── SyncView.ts               同步中心：差异预览、文件选择与本地提交确认
    ├── workbenchSyncRemote.ts     同步 Remote 的客户端适配层
    ├── HostView.ts               低频宿主诊断页（正常时不占首页）
    ├── history.ts                前进/后退的 HistoryStore（栈 + 游标）
    ├── parts.ts                  跨视图共用的小件：区块标题、提示、状态条
    ├── Trigger.ts                侧栏底部入口
    ├── store.ts                  极简可观察 store + React 绑定
    ├── tokens.ts                 主题令牌（--dsw-alias-*）与共用样式
    ├── views.ts                  view id 编解码、PANEL_ID、项目位命名
    ├── i18n.ts                   Translate 类型
    └── projects/
        ├── types.ts              ★ 项目接口契约 + 岗位记录/Remote 的类型
        ├── slots.ts              详情页项目顺序与内部预留位
        ├── host.ts               单个项目位的渲染（项目本体 or 预留卡片）
        ├── jobRadarRemote.ts     Job Radar 网关命名空间适配层
        ├── jobRadar.ts           项目 01：Job Radar
        ├── tablewareRadarRemote.ts Tableware Radar 网关命名空间适配层
        └── tablewareRadar.ts     项目 02：出海业务用户调研
projects/
├── job-hunting/                  原 Job Radar 仓库完整迁入
└── tableware-radar/              原 Tableware Radar 仓库完整迁入
scripts/
├── dev.mjs                       构建 + 冒烟 + 重装 + 校验
├── smoke-client.mjs              无浏览器冒烟测试
├── browser-check.py              真实 host + 真实浏览器的端到端检查
└── shots/                        browser-check 的截图落点
```

## 两个插槽

| 插槽 | 用途 | 注册 id / key |
| --- | --- | --- |
| `sidebar.footer.action` | 侧栏底部的入口按钮，owner props 是 `{ wide }` | `workbench` |
| `main` | 主区域面板，被选中时占据中间那一列 | key = `workbench` |

两个 id 是**同一个字符串**（`views.ts` 里的 `PANEL_ID`），因为 layout 就是靠它连起来的：
中间渲染"key 等于 `panelInfo.activePanelId` 的那个 `main` 条目"，而侧栏点一下是调 `ctx.layout.selectPanel(id)`。
所以这不叫"打开一个面板"，叫**切走主视图**。

`main` 是 keyed 插槽 —— 别的插件可以各自注册自己的 key，互不覆盖；工作台只是其中一个。
`selectPanel(null)` 把主区域还给对话。

**数据来源**：宿主自带的 `pluginInventory/list` 加上根插件统一挂载的 `remote.jobRadar`、`remote.tablewareRadar` 和 `remote.workbenchSync`。业务源码与精选结果都来自本仓库；旧业务仓库已归档，不再单独安装。

**主题**：详情页继续使用 `tokens.ts` 中的宿主主题令牌。首页按已确认的“暮光任务舱”设计使用独立暗色语义令牌，完整规范见 [`DESIGN.md`](DESIGN.md)，产品约束见 [`PRODUCT.md`](PRODUCT.md)。

**导航状态**：`history.ts` 里一个栈 + 游标的 `HistoryStore`。进入项目或同步视图会 `push`，前进/后退只挪游标，从历史里往回走后再进入新视图会截断前面的分叉 —— 和浏览器一样。栈深上限 50。
视图 id 编解码在 `views.ts`（`control-room` / `host` / `slot:N`），`clampViewId` 会把越界的 id 修回控制台，
这样删掉一个项目位不会让停在那一位的历史记录把面板渲染成空白。

## 常见扩展

| 想做的事 | 改哪里 |
| --- | --- |
| 加/减详情项目 | `projects/slots.ts`，并在 `ControlRoom.ts` 设计对应的首页摘要组件 |
| 加一个非项目视图 | `views.ts` 增加 view id，`Workbench.ts` 接路由，首页只在确有高频价值时增加入口 |
| 改主区域面板的排版 | `Workbench.ts` 的 `chrome()`（标题栏）与 `body()`（内容区） |
| 给入口换个图标 | `Trigger.ts` 的 `glyph()` |
| 加一个快捷键 | `Workbench.ts` 挂载期那段 `keydown` 监听（现有 `Alt+←/→`） |
| 给项目更多宿主数据 | `projects/types.ts` 加字段 + `client/index.ts` 的 `apply()` 里传值 |
| 消费别的插件的 Remote | 照 `jobRadar.ts` + `jobRadarRemote.ts` 抄：`ctx.reflect.get('remote.X')` → 适配层拆信封/补实参 → 每次调用重新解析 → 缺席时渲染状态 |
| 项目间共享状态 | 在 `apply()` 里 `createValueStore()`，把 store 放进 `projectCtx` |

## 排错

| 现象 | 原因 |
| --- | --- |
| 侧栏入口点得动，但主区域没变 | **host 是 0.1.1 或更早**：没有 `main` 插槽，也没有 `ctx.layout.selectPanel`。升到 >= 0.1.5-rc.2（见下） |
| 改了代码，页面没变 | profile 里还是旧拷贝。跑 `node scripts/dev.mjs` —— 它会比对副本与产物并在不一致时强制重装 |
| 侧栏没有入口 | 宿主半部没挂上：`dsh --profile web --dump-config \| grep workbench` |
| 新项目详情可访问但首页没有入口 | 首页不自动映射 slot；需要在 `ControlRoom.ts` 增加有真实摘要数据的组件 |
| 项目点进去空白 | 项目的 `render` 返回了 `null` |
| 项目显示「渲染失败」 | 项目的 `render` 抛异常了，卡片上会带原始错误信息 |
| 前进/后退按钮是灰的 | 历史里只有一项（还没进入项目），或游标已经在某一端 |
| 项目 01 说「数据源未装载」 | 统一插件客户端 Remote 尚未挂载完成，或 profile 仍在使用旧副本；先刷新，再运行 `node scripts/dev.mjs` 重装 |
| 项目 01 说读取失败 | `remote.jobRadar` 在但调用出错，卡片上会带原始错误；`jobs.json` 不存在时会返回空列表而不是报错。若是 `expected N argument(s), got M`，是描述符与调用方的实参个数不一致 |
| 列表渲染出来了但是空的 | 信封没拆：`res.jobs` 是 `undefined`。检查适配层有没有 `unwrap` |
| 控制台 `cannot get property "typert" without inject` | 调 `$mount` 的那个插件，`inject` 里少了 `typert` |

### 宿主版本

工作台需要 dsh **>= 0.1.5-rc.2**（`main` 插槽 + `ctx.layout.selectPanel` 都是 0.1.5 的 layout 才有的）。

```bash
npm i -g @deepseek-ai/dsh@latest     # 装到全局，拿一个稳定路径
dsh --version
```

**别用 `npx`。** npx 按 install-spec 的哈希缓存目录，`...\_npx\<hash>\...\bin.js` 会把 host 悄悄钉在当初解析到的那个版本上 —— 你升级了 npm 上的 latest，跑起来的还是老的。重启脚本因此指向全局路径（`~/.dsh/restart-dsh-web.ps1`）。

profile 的依赖不是自己装的：host 启动时会在 `$DSH_HOME/profiles/node_modules` 维护一个**扁平回退目录**，
把每个包**符号链接**到自己那份依赖闭包里。所以换一个完整的新版 host 启动，它会自动把这一堆链接重指过去 ——
不用手改 profile。`profiles/node_modules` 只有几百 KB 就是这个原因（全是链接）。
（详见 `@deepseek-ai/dsh-app-boot` 的 `profile.d.ts`。它遇到同名**真实目录**会直接抛错，
所以别往那个目录里手写东西。）

模块加载器只把 `react` 提供给插件；不要 `import` `react-dom` 或 `@deepseek-ai/dsh-client-ui-*`，它们在运行时并不在模块表里。
