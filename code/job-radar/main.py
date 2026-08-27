"""job-radar 命令行入口。

用法:
  python main.py add "JD文本" [--title 标题] [--company 公司] [--url 链接]
  python main.py add-file path/to/jd.txt [--title 标题]
  python main.py fetch               # 从聚合源抓取
  python main.py list [--grade S] [--status new]
  python main.py score               # 对全部岗位重新打分(改画像后)
  python main.py mark <id> <status>  # 状态: new/applied/interested/rejected
  python main.py serve [--port 8000] # 启动本地仪表盘
  python main.py export              # 导出 JSON 快照
  python main.py import [file.json]  # 从 JSON 快照重建本地库
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from src.collector import collect, load_sources
from src.parser import parse_jd
from src.scorer import Scorer, grade_label
from src.storage import Storage

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


def load_profile() -> dict:
    with open(CONFIG_DIR / "profile.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_storage() -> Storage:
    return Storage(DATA_DIR)


def plus_skill_names(profile: dict) -> list[str]:
    return [p["name"] for p in profile.get("plus_skills", [])]


def process_jd(text: str, profile: dict, scorer: Scorer,
               title: str = "", company: str = "", url: str = "",
               source: str = "manual") -> tuple[str, dict]:
    """解析 + 打分 + 入库,返回 (job_id, job_dict)。"""
    parsed = parse_jd(text, plus_skills=plus_skill_names(profile),
                      title=title, company=company, url=url)
    result = scorer.score(parsed)
    storage = make_storage()
    jid = storage.upsert_job(parsed, score=result, source=source)
    job = storage.get(jid)
    storage.close()
    return jid, job


# ---------- 子命令 ----------

def cmd_add(args: argparse.Namespace) -> int:
    profile = load_profile()
    scorer = Scorer(profile)
    jid, job = process_jd(
        args.text, profile, scorer,
        title=args.title, company=args.company, url=args.url,
    )
    print(f"✅ 已入库  [{job['grade']}] {job['title']}  id={jid}")
    print(f"   公司:{job['company']}  城市:{job['city'] or '-'}  "
          f"薪资:{job['salary_min']}-{job['salary_max'] or '?'}")
    if job["reasons"]:
        print(f"   ⚠️ 未通过:{job['reasons']}")
    else:
        print(f"   评分:{job['score']}  {grade_label(job['grade'])}")
    return 0


def cmd_add_file(args: argparse.Namespace) -> int:
    p = Path(args.path)
    if not p.exists():
        print(f"❌ 文件不存在:{p}")
        return 1
    text = p.read_text(encoding="utf-8")
    profile = load_profile()
    scorer = Scorer(profile)
    jid, job = process_jd(text, profile, scorer,
                          title=args.title or p.stem, company=args.company)
    print(f"✅ 已入库  [{job['grade']}] {job['title']}  id={jid}  评分:{job['score']}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    profile = load_profile()
    scorer = Scorer(profile)
    storage = make_storage()
    sources = load_sources()
    enabled = [s for s in sources if s.enabled]
    if not enabled:
        print("ℹ️  没有启用的订阅源。编辑 config/sources.yaml 添加后重试。")
        storage.close()
        return 0

    def on_job(parsed, src_name):
        result = scorer.score(parsed)
        storage.upsert_job(parsed, score=result, source=src_name)

    print(f"🔍 抓取 {len(enabled)} 个订阅源...")
    n = collect(enabled, plus_skill_names(profile), on_job=on_job)
    stats = storage.stats()
    storage.close()
    print(f"✅ 采集完成:解析 {n} 条,库内共 {stats['total']} 条")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    storage = make_storage()
    jobs = storage.all_jobs(grade=args.grade, status=args.status)
    storage.close()
    if not jobs:
        print("ℹ️  暂无岗位。用 `add` 或 `fetch` 添加。")
        return 0
    print(f"{'id':<14} {'等级':<4} {'状态':<10} {'标题':<30} {'公司':<16} 评分")
    print("-" * 90)
    for j in jobs:
        status = {"new": "新", "applied": "已投", "interested": "意向", "rejected": "弃"}[j["status"]]
        title = (j["title"] or "(无标题)")[:28]
        print(f"{j['id']:<14} {j['grade']:<4} {status:<10} {title:<30} {(j['company'] or '-')[:14]:<16} {j['score']}")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    profile = load_profile()
    scorer = Scorer(profile)
    storage = make_storage()
    jobs = storage.all_jobs()
    changed = 0
    for j in jobs:
        parsed = parse_jd(
            j["raw"], plus_skills=plus_skill_names(profile),
            title=j["title"], company=j["company"], url=j["url"],
        )
        result = scorer.score(parsed)
        if result.total != j["score"] or result.grade != j["grade"]:
            storage.upsert_job(parsed, score=result, source=j["source"])
            changed += 1
    stats = storage.stats()
    storage.close()
    print(f"✅ 重新打分完成:变更 {changed} 条,共 {stats['total']} 条")
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    storage = make_storage()
    ok = storage.set_status(args.id, args.status)
    storage.close()
    if ok:
        print(f"✅ {args.id} → {args.status}")
        return 0
    print(f"❌ 未找到 id={args.id}")
    return 1


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    print(f"🚀 仪表盘启动: http://127.0.0.1:{args.port}")
    print("   按 Ctrl+C 停止")
    uvicorn.run("src.webapp:app", host="127.0.0.1", port=args.port, reload=False)


def cmd_export(args: argparse.Namespace) -> int:
    storage = make_storage()
    storage.export_json()
    print(f"✅ 已导出:{storage.json_path}")
    storage.close()
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    storage = make_storage()
    n = storage.import_json(args.file)
    storage.close()
    print(f"✅ 导入 {n} 条")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="job-radar", description="岗位筛选器")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("add", help="手动添加 JD 文本")
    pa.add_argument("text")
    pa.add_argument("--title", default="")
    pa.add_argument("--company", default="")
    pa.add_argument("--url", default="")
    pa.set_defaults(func=cmd_add)

    pf = sub.add_parser("add-file", help="从文件添加 JD")
    pf.add_argument("path")
    pf.add_argument("--title", default="")
    pf.add_argument("--company", default="")
    pf.set_defaults(func=cmd_add_file)

    pc = sub.add_parser("fetch", help="从聚合源抓取")
    pc.set_defaults(func=cmd_fetch)

    pl = sub.add_parser("list", help="列出岗位")
    pl.add_argument("--grade", default=None, help="按等级过滤 S/A/B/C")
    pl.add_argument("--status", default=None, help="按状态过滤 new/applied/...")
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("score", help="重新打分全部岗位")
    ps.set_defaults(func=cmd_score)

    pm = sub.add_parser("mark", help="标记岗位状态")
    pm.add_argument("id")
    pm.add_argument("status", choices=["new", "applied", "interested", "rejected"])
    pm.set_defaults(func=cmd_mark)

    pv = sub.add_parser("serve", help="启动仪表盘")
    pv.add_argument("--port", type=int, default=8000)
    pv.set_defaults(func=cmd_serve)

    pe = sub.add_parser("export", help="导出 JSON 快照")
    pe.set_defaults(func=cmd_export)

    pi = sub.add_parser("import", help="从 JSON 快照导入")
    pi.add_argument("file", nargs="?", default=None)
    pi.set_defaults(func=cmd_import)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
