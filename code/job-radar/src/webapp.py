"""本地仪表盘后端(FastAPI)。

接口:
  GET  /                     → 前端页面
  GET  /api/jobs             → 岗位列表(?grade=S&status=new)
  GET  /api/jobs/{jid}       → 单岗位详情
  POST /api/jobs/{jid}/status → 更新投递状态 {"status": "applied"}
  GET  /api/stats            → 统计
  POST /api/jobs             → 手动添加 JD {"text": "...", "title": "..."}
"""
from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .parser import parse_jd
from .scorer import Scorer
from .storage import Storage, ALL_STATUS

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"

app = FastAPI(title="Job Radar", description="岗位筛选器本地仪表盘")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态资源
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


def _storage() -> Storage:
    return Storage(DATA_DIR)


def _profile() -> dict:
    with open(ROOT / "config" / "profile.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


class JobAddBody(BaseModel):
    text: str
    title: str = ""
    company: str = ""
    url: str = ""


class StatusBody(BaseModel):
    status: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/api/jobs")
def list_jobs(grade: str | None = None, status: str | None = None) -> dict:
    storage = _storage()
    try:
        jobs = storage.all_jobs(grade=grade, status=status)
        return {"jobs": jobs, "total": len(jobs)}
    finally:
        storage.close()


@app.get("/api/jobs/{jid}")
def get_job(jid: str) -> dict:
    storage = _storage()
    try:
        job = storage.get(jid)
        if job is None:
            raise HTTPException(404, f"岗位不存在:{jid}")
        return job
    finally:
        storage.close()


@app.post("/api/jobs")
def add_job(body: JobAddBody) -> dict:
    profile = _profile()
    scorer = Scorer(profile)
    storage = _storage()
    try:
        plus = [p["name"] for p in profile.get("plus_skills", [])]
        parsed = parse_jd(
            body.text, plus_skills=plus,
            title=body.title, company=body.company, url=body.url,
        )
        result = scorer.score(parsed)
        jid = storage.upsert_job(parsed, score=result)
        return storage.get(jid)
    finally:
        storage.close()


@app.post("/api/jobs/{jid}/status")
def set_status(jid: str, body: StatusBody) -> dict:
    if body.status not in ALL_STATUS:
        raise HTTPException(400, f"非法状态:{body.status},可选 {ALL_STATUS}")
    storage = _storage()
    try:
        if not storage.set_status(jid, body.status):
            raise HTTPException(404, f"岗位不存在:{jid}")
        return {"ok": True, "id": jid, "status": body.status}
    finally:
        storage.close()


@app.get("/api/stats")
def stats() -> dict:
    storage = _storage()
    try:
        return storage.stats()
    finally:
        storage.close()


@app.get("/api/profile")
def profile() -> dict:
    return _profile()
