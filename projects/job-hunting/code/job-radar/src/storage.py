"""存储层:SQLite 本地库 + JSON 快照导出(git 同步用)。

同步策略(见 docs/需求与方案 §2):
- SQLite 二进制不进 git(双机同时写会冲突)
- 每次写入后导出 jobs.json 快照,由 git 同步
- 拉取后从 jobs.json 可重建本地库(import_json)
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .parser import ParsedJD
from .scorer import ScoreResult

STATUS_NEW = "new"
STATUS_APPLIED = "applied"
STATUS_REJECTED = "rejected"
STATUS_INTERESTED = "interested"

ALL_STATUS = [STATUS_NEW, STATUS_APPLIED, STATUS_REJECTED, STATUS_INTERESTED]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _timestamp(value: str | None) -> datetime:
    """Parse snapshot/SQLite timestamps from either Python (+00:00) or JS (Z)."""
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


class Storage:
    """岗位数据存储:SQLite + JSON 快照。"""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "jobs.db"
        self.json_path = self.data_dir / "jobs.json"
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                city TEXT,
                salary_min INTEGER DEFAULT 0,
                salary_max INTEGER DEFAULT 0,
                experience_min INTEGER DEFAULT 0,
                experience_max INTEGER DEFAULT 0,
                education TEXT DEFAULT '',
                url TEXT DEFAULT '',
                source TEXT DEFAULT 'manual',
                published TEXT DEFAULT '',
                raw TEXT DEFAULT '',
                score REAL DEFAULT 0,
                grade TEXT DEFAULT 'C',
                status TEXT DEFAULT 'new',
                reasons TEXT DEFAULT '[]',
                details TEXT DEFAULT '{}',
                created_at TEXT,
                updated_at TEXT
            );
            """
        )
        self._conn.commit()

    # ---------- 写入 ----------

    def upsert_job(
        self,
        parsed: ParsedJD,
        score: ScoreResult | None = None,
        source: str = "manual",
        jid: str | None = None,
    ) -> str:
        """插入或更新岗位(按 url+title 去重)。返回 job id。"""
        if jid is None:
            jid = self._find_by_url(parsed.url, parsed.title)
        exists = jid is not None and self._conn.execute(
            "SELECT 1 FROM jobs WHERE id=?", (jid,)
        ).fetchone() is not None
        now = _now()
        score = score or ScoreResult()
        if not exists:
            jid = jid or uuid.uuid4().hex[:12]
            self._conn.execute(
                """
                INSERT INTO jobs (id, title, company, city, salary_min, salary_max,
                    experience_min, experience_max, education, url, source, published,
                    raw, score, grade, status, reasons, details, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    jid, parsed.title, parsed.company, parsed.city,
                    parsed.salary_min, parsed.salary_max,
                    parsed.experience_min, parsed.experience_max,
                    parsed.education, parsed.url, source, parsed.published,
                    parsed.raw, score.total, score.grade, STATUS_NEW,
                    json.dumps(score.reasons, ensure_ascii=False),
                    json.dumps(score.details, ensure_ascii=False),
                    now, now,
                ),
            )
        else:
            self._conn.execute(
                """
                UPDATE jobs SET title=?, company=?, city=?, salary_min=?,
                    salary_max=?, experience_min=?, experience_max=?, education=?,
                    url=?, published=?, raw=?, score=?, grade=?, reasons=?,
                    details=?, updated_at=?
                WHERE id=?
                """,
                (
                    parsed.title, parsed.company, parsed.city,
                    parsed.salary_min, parsed.salary_max,
                    parsed.experience_min, parsed.experience_max,
                    parsed.education, parsed.url, parsed.published,
                    parsed.raw, score.total, score.grade,
                    json.dumps(score.reasons, ensure_ascii=False),
                    json.dumps(score.details, ensure_ascii=False),
                    now, jid,
                ),
            )
        self._conn.commit()
        self.export_json()
        return jid

    def _find_by_url(self, url: str, title: str) -> str | None:
        if not url:
            return None
        row = self._conn.execute(
            "SELECT id FROM jobs WHERE url = ? LIMIT 1", (url,)
        ).fetchone()
        return row["id"] if row else None

    def set_status(self, jid: str, status: str) -> bool:
        if status not in ALL_STATUS:
            raise ValueError(f"非法状态:{status}")
        cur = self._conn.execute(
            "UPDATE jobs SET status=?, updated_at=? WHERE id=?",
            (status, _now(), jid),
        )
        self._conn.commit()
        self.export_json()
        return cur.rowcount > 0

    # ---------- 查询 ----------

    def all_jobs(
        self,
        grade: str | None = None,
        status: str | None = None,
        days: int | None = None,
    ) -> list[dict]:
        sql = "SELECT * FROM jobs WHERE 1=1"
        params: list = []
        if grade:
            sql += " AND grade=?"
            params.append(grade)
        if status:
            sql += " AND status=?"
            params.append(status)
        if days:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
                timespec="seconds"
            )
            sql += " AND created_at >= ?"
            params.append(cutoff)
        sql += " ORDER BY score DESC"
        rows = self._conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["reasons"] = json.loads(d["reasons"] or "[]")
            d["details"] = json.loads(d["details"] or "{}")
            out.append(d)
        return out

    def get(self, jid: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["reasons"] = json.loads(d["reasons"] or "[]")
        d["details"] = json.loads(d["details"] or "{}")
        return d

    def stats(self) -> dict:
        today_cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(
            timespec="seconds"
        )
        row = self._conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN grade='S' THEN 1 ELSE 0 END) AS s_count, "
            "SUM(CASE WHEN grade='A' THEN 1 ELSE 0 END) AS a_count, "
            "SUM(CASE WHEN status='applied' THEN 1 ELSE 0 END) AS applied_count, "
            "SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS today_count, "
            "SUM(CASE WHEN status='new' THEN 1 ELSE 0 END) AS new_count "
            "FROM jobs",
            (today_cutoff,),
        ).fetchone()
        return dict(row)

    # ---------- JSON 快照 ----------

    def _merge_newer_snapshot_statuses(self) -> None:
        """Preserve status changes written by the unified DSH workbench.

        ``jobs.json`` is the cross-device source of truth. The browser updates
        that snapshot directly, while the Python pipeline keeps a rebuildable
        SQLite index. Before Python exports the database again, bring across a
        newer snapshot status so a later fetch/score cannot silently undo a
        status selected in the workbench.
        """
        if not self.json_path.exists():
            return
        try:
            snapshot = json.loads(self.json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        changed = False
        for job in snapshot.get("jobs", []):
            jid = job.get("id")
            status = job.get("status")
            if not jid or status not in ALL_STATUS:
                continue
            row = self._conn.execute(
                "SELECT status, updated_at FROM jobs WHERE id=?", (jid,)
            ).fetchone()
            if row is None or _timestamp(job.get("updated_at")) <= _timestamp(row["updated_at"]):
                continue
            self._conn.execute(
                "UPDATE jobs SET status=?, updated_at=? WHERE id=?",
                (status, job.get("updated_at") or _now(), jid),
            )
            changed = True
        if changed:
            self._conn.commit()

    def export_json(self) -> None:
        """导出全量快照到 jobs.json(供 git 同步)。"""
        self._merge_newer_snapshot_statuses()
        jobs = self.all_jobs()
        payload = {
            "version": 1,
            "exported_at": _now(),
            "jobs": jobs,
        }
        tmp = self.json_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, self.json_path)

    def import_json(self, path: str | Path | None = None) -> int:
        """从 JSON 快照重建本地库,返回导入条数。"""
        src = Path(path) if path else self.json_path
        if not src.exists():
            return 0
        data = json.loads(src.read_text(encoding="utf-8"))
        count = 0
        for j in data.get("jobs", []):
            parsed = ParsedJD(
                title=j.get("title", ""),
                company=j.get("company", ""),
                city=j.get("city", ""),
                salary_min=j.get("salary_min", 0),
                salary_max=j.get("salary_max", 0),
                experience_min=j.get("experience_min", 0),
                experience_max=j.get("experience_max", 0),
                education=j.get("education", ""),
                url=j.get("url", ""),
                published=j.get("published", ""),
                raw=j.get("raw", ""),
            )
            jid = j.get("id")
            if jid:
                self.upsert_job(parsed, source=j.get("source", "import"), jid=jid)
            else:
                jid = self.upsert_job(parsed, source=j.get("source", "import"))
            # 恢复打分与状态
            self._conn.execute(
                "UPDATE jobs SET score=?, grade=?, status=?, reasons=?, details=?, "
                "created_at=?, updated_at=? WHERE id=?",
                (
                    j.get("score", 0), j.get("grade", "C"), j.get("status", "new"),
                    json.dumps(j.get("reasons", []), ensure_ascii=False),
                    json.dumps(j.get("details", {}), ensure_ascii=False),
                    j.get("created_at", _now()), j.get("updated_at", _now()), jid,
                ),
            )
            count += 1
        self._conn.commit()
        # 关键:重建完成后必须再导出一份快照。否则 upsert_job 在循环内
        # 已触发 export_json,最后一条岗位的 score/grade/reasons/details
        # 会停留在「恢复打分」UPDATE 之前的默认值,导致往返不幂等。
        self.export_json()
        return count

    def close(self) -> None:
        self._conn.close()
