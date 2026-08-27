# Job Radar · 岗位筛选器

自动筛选网上岗位信息的本地工具:聚合源采集 → JD 解析 → 画像打分 → 仪表盘展示。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 手动添加一条 JD 试试(V0 最小闭环)
python main.py add "岗位:高级Python后端工程师 公司:示例科技 城市:北京 薪资:25-40K 要求:本科,3-5年经验,精通Python、FastAPI、Redis,有高并发经验" --title "高级Python后端工程师" --company "示例科技"

# 3. 查看打分结果
python main.py list --grade S

# 4. 启动本地仪表盘
python main.py serve
# 浏览器打开 http://127.0.0.1:8000
```

## 常用命令

| 命令 | 说明 |
|---|---|
| `python main.py add "JD文本"` | 手动添加并打分 |
| `python main.py add-file jd.txt` | 从文件添加 |
| `python main.py fetch` | 从聚合源抓取(需先配置 sources.yaml) |
| `python main.py list [--grade S]` | 查看岗位列表 |
| `python main.py score` | 改画像后重新打分 |
| `python main.py mark <id> applied` | 标记投递状态 |
| `python main.py serve` | 启动仪表盘 |
| `python main.py export/import` | JSON 快照导出/导入(跨机器同步) |

## 配置

- `config/profile.yaml` — 求职画像(城市/薪资/经验/学历/技能/权重),**所有筛选参数都在这**
- `config/sources.yaml` — RSS 聚合订阅源

## 数据同步(公司/家庭双电脑)

- 代码与画像配置 → git 同步
- 岗位数据 → `data/jobs.json` 快照进 git,每台机器 `python main.py import` 重建本地库
- 详细策略见 `docs/岗位筛选器-需求与方案.md`

## 目录结构

```
job-radar/
├── main.py              # CLI 入口
├── config/
│   ├── profile.yaml     # 求职画像
│   └── sources.yaml     # 聚合源
├── src/
│   ├── parser.py        # JD 解析(正则规则,可换 LLM)
│   ├── scorer.py        # 打分引擎(硬过滤+软评分)
│   ├── storage.py       # SQLite + JSON 快照
│   ├── collector.py     # RSS 聚合源采集
│   └── webapp.py        # FastAPI 仪表盘
├── web/index.html       # 仪表盘前端(单页无框架)
└── data/                # 本地数据(SQLite 不入 git,JSON 入)
```
