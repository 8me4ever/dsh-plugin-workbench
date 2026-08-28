# dsh-job-radar — Job Radar 岗位看板(DSH 插件)

把 Job Radar 岗位筛选器的看板整合进 DeepSeek Harness Web GUI:在 DSH 设置页直接浏览/筛选/标记你的求职岗位,与本地 job-radar 共享同一份 `jobs.json` 数据,无需单独启动 FastAPI 服务。

## 功能

- **设置页面板**:DSH 设置页出现「Job Radar 岗位看板」入口
- **岗位列表**:总数/S/A/B 统计、按等级(S/A/B/C)和状态(新发现/已投递/有意向/已放弃)筛选
- **状态标记**:一键切换投递状态,实时写回 `jobs.json`
- **数据同步**:与本地 `python main.py serve` 看板共享同一数据文件,两边操作互通

## 目录结构

```
dsh-job-radar/
├── package.json          # 插件清单(dsh.bundle / dsh.client 声明)
├── cordis.patch.yml      # 服务端插件注册
├── build.mjs             # esbuild 构建(自动定位 npx 缓存的 esbuild)
├── src/
│   ├── index.ts          # 服务端:读 jobs.json + 状态标记(零外部依赖)
│   └── client/
│       ├── index.ts      # 客户端:注册 settings.section 插槽
│       └── RadarPanel.ts # 看板 React 组件(手写 createElement,无 JSX 依赖)
├── lib/index.js          # 构建产物:服务端 bundle
└── client/client.js      # 构建产物:浏览器 bundle(__ModuleLoader__ 格式)
```

## 安装(在 DSH 机器上)

```bash
# 1. 构建
cd code/job-radar/plugin/dsh-job-radar
node build.mjs

# 2. 安装进 DSH web profile(自动加入 bundles 列表)
dsh plugin --profile web add "file:D:\...\code\job-radar\plugin\dsh-job-radar"

# 3. 配置 dataDir(指向 job-radar 数据目录,含 jobs.json)
#    编辑 ~/.dsh/profiles/web/cordis.patch.yml:
#    - id: dsh-job-radar
#      config:
#        dataDir: "D:\\...\\code\\job-radar\\data"

# 4. 重启 DSH web
powershell -File ~/.dsh/restart-dsh-web.ps1
```

## 刷新使用

重启后刷新 DSH 页面 → 设置页 → 「Job Radar 岗位看板」。

## 数据说明

- 服务端直接读 `dataDir/jobs.json`(storage.export_json 的产物:`{version, exported_at, jobs[]}`)
- 状态标记会写回该文件,格式与 job-radar 的 `export` 命令一致,双向兼容
- 机器迁移:改 `cordis.patch.yml` 的 `dataDir` 指向本机路径即可
