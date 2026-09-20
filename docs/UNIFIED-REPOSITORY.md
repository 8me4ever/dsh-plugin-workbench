# 统一仓库约定

`dsh-plugin-workbench` 是唯一维护、同步和安装的仓库。原来的 Job Radar 与
Tableware Radar 代码完整保留在 `projects/` 下，但不再作为独立安装单元。

## 目录

- `src/`：唯一的 DSH 插件。宿主端同时提供 `remote.jobRadar` 与
  `remote.tablewareRadar`，客户端提供工作台及两个项目页面。
- `projects/job-hunting/`：岗位采集、解析、评分、SQLite 本地索引及
  `jobs.json` 精选快照。
- `projects/tableware-radar/`：Amazon UK 评论分析管道、维度配置及
  `analysis.json` 精选快照。

## Git 数据边界

提交并跨设备同步：

- 全部源码、测试和非敏感配置；
- `projects/job-hunting/code/job-radar/data/jobs.json`；
- `projects/tableware-radar/data/analysis.json`（生成后）；
- Tableware 的维度与 ASIN 配置。

保持本地：

- Job Radar SQLite、BOSS 登录态和抓取临时文件；
- Tableware 原始评论、清洗结果、标签中间产物与日志；
- Node/Python 依赖、构建缓存、浏览器数据和密钥。

## 本机安装

在仓库根目录运行：

```powershell
npm ci
npm run verify
npm run dev
```

`npm run dev` 会把当前 checkout 的绝对路径写到本机
`~/.dsh/dsh-plugin-workbench.json`。DSH profile 中安装的是打包副本，但两个
Remote 始终通过这个本机登记读取 Git checkout 内的精选快照，因此页面写入、
Python 管道和 Git 同步使用同一份数据。

也可用插件配置 `workspaceDir` 或环境变量 `DSH_WORKBENCH_ROOT` 覆盖登记位置。

## 验证

`npm run verify` 依次执行工作台构建、客户端冒烟、Job Radar 测试和
Tableware Radar 测试。只有该命令全部通过后才允许推送或安装。

旧业务插件目录仍保留作为迁移来源和历史参考，但不应再单独执行其中的
`dsh plugin add`；对外只安装仓库根目录的 `dsh-plugin-workbench`。
