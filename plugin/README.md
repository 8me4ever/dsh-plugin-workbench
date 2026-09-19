# dsh-tableware-radar · 数据面插件

把 Python 管道产出的唯一真源 `data/analysis.json` 经 `remote.tablewareRadar` 暴露给浏览器
（工作台项目 02 页面）。**页面代码不在这里**——它住在 `dsh-plugin-workbench` 仓库
（见 `docs/ARCHITECTURE.md` §1.5）。

## 契约（0 参数）

| 方法 | 参数 | 返回 |
| --- | --- | --- |
| `getAnalysis()` | **0** | `Analysis \| null`（文件不存在→`null`） |
| `getStatus()` | **0** | `{ present, path, mtimeMs, bytes, generatedAt }` |

⚠️ 网关按 TYPERT 清单声明的 `parameters.length` **严格校验实参个数**，故两方法均为 0 参数。
新增带参方法时必须同步三处：宿主 `TYPERT` 清单 + 客户端贡献描述符 + 页面适配层补实参。

## 构建

```powershell
cd F:\Samuel\dsh-plugins\dsh-tableware-radar\plugin
npm i -D esbuild      # 若本机/全局都没有 esbuild
npm run build         # → lib/index.js, lib/typert.host.js, lib/client.js
```

## 安装进 web profile

```powershell
# 一条命令完成 build + 安装 + 校验副本一致
node scripts/dev.mjs --profile web

# 或手动
dsh plugin --profile web add "file:F:/Samuel/dsh-plugins/dsh-tableware-radar/plugin"
```

安装后**重启宿主**并刷新浏览器：

```powershell
dsh web --profile web
```

宿主日志应出现：`[dsh-tableware-radar] data face mounted; analysis=...`。

## 数据目录

默认读取 `F:/Samuel/dsh-plugins/dsh-tableware-radar/data/analysis.json`。
可用插件配置 `dataDir` 或环境变量 `TABLEWARE_DATA_DIR` 覆盖。

## 排查（对齐 ARCHITECTURE §1.6 / U2 / U3）

- **浏览器控制台 `cannot get property "typert" without inject`** → 在 `src/client/index.js` 的
  `inject` 里补 `'typert'`（先试 `['remote']`）。
- **`client api: ... has no strict codec`** → 客户端贡献描述符的 codec 必须是 `{mode:'strict', …}`；
  本插件已在 `src/schemas.js` 保证两半共用同一 strict codec。
- **`arguments-invalid`** → 方法参数个数与清单不符；本项目两方法均为 0 参数，不应触发。
- **页面显示“数据面未装载”** → 插件未装或宿主未重启；参考上面“安装进 web profile”。
- **页面显示“尚未跑过流水线”** → `analysis.json` 不存在；跑 `python -m tableware_radar.cli run --all`。
