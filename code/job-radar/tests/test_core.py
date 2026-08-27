"""job-radar 核心逻辑单元测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser import parse_jd  # noqa: E402
from src.scorer import Scorer  # noqa: E402

PROFILE = {
    "cities": ["北京", "深圳"],
    "salary_min": 15000,
    "experience": {"min": 1, "max": 8},
    "education": "本科",
    "must_skills": ["Python", "Golang", "Java"],
    "plus_skills": [
        {"name": "FastAPI", "weight": 10},
        {"name": "Redis", "weight": 8},
        {"name": "高并发", "weight": 8},
    ],
    "weights": {
        "skill": 40, "experience": 20, "company": 15,
        "freshness": 10, "commute": 10, "other": 5,
    },
    "grades": {"S": 85, "A": 70, "B": 55, "C": 0},
    "company_plus": ["融资", "上市"],
    "benefit_plus": ["六险一金", "弹性工作"],
}


def make_scorer() -> Scorer:
    return Scorer(PROFILE)


# ---------- 解析 ----------

class TestParse:
    def test_salary_k(self):
        jd = parse_jd("薪资:25-40K", plus_skills=[])
        assert jd.salary_min == 25000
        assert jd.salary_max == 40000

    def test_salary_wan(self):
        jd = parse_jd("月薪2-3万", plus_skills=[])
        assert jd.salary_min == 20000
        assert jd.salary_max == 30000

    def test_salary_usd_annual(self):
        # $150K-$300K 年薪 → 人民币月薪(1USD≈7.2, 年薪/12)
        jd = parse_jd("Salary $150K - $300K", plus_skills=[])
        assert jd.salary_min == 90000
        assert jd.salary_max == 180000

    def test_salary_usd_not_confused_with_trial(self):
        # "1-3 days, $1-3K" 这类 trial 报酬不应被当主薪资
        jd = parse_jd("Paid work trial: 1-3 days, $1-3K. Salary $150K - $300K", plus_skills=[])
        assert jd.salary_min == 90000
        assert jd.salary_max == 180000

    def test_experience_range(self):
        jd = parse_jd("要求3-5年经验", plus_skills=[])
        assert jd.experience_min == 3
        assert jd.experience_max == 5

    def test_experience_unlimited(self):
        jd = parse_jd("经验不限", plus_skills=[])
        assert jd.experience_min == 0
        assert jd.experience_max == 0

    def test_education(self):
        jd = parse_jd("要求硕士学历", plus_skills=[])
        assert jd.education == "硕士"

    def test_city(self):
        jd = parse_jd("工作地点:北京", plus_skills=[])
        assert jd.city == "北京"

    def test_skills_hit(self):
        jd = parse_jd("精通 FastAPI 和 Redis", plus_skills=["FastAPI", "Redis"])
        assert set(jd.skills) == {"FastAPI", "Redis"}


# ---------- 硬性过滤 ----------

class TestHardFilter:
    def test_city_mismatch(self):
        jd = parse_jd("工作地点:上海 薪资:30-50K 本科 3-5年 Python", plus_skills=[])
        r = make_scorer().score(jd)
        assert not r.passed
        assert any("城市" in x for x in r.reasons)

    def test_salary_too_low(self):
        jd = parse_jd("工作地点:北京 薪资:8-12K 本科 3-5年 Python", plus_skills=[])
        r = make_scorer().score(jd)
        assert not r.passed
        assert any("薪资" in x for x in r.reasons)

    def test_missing_must_skill(self):
        jd = parse_jd("工作地点:北京 薪资:30-50K 本科 3-5年 精通前端React", plus_skills=[])
        r = make_scorer().score(jd)
        assert not r.passed
        assert any("必须技能" in x for x in r.reasons)

    def test_education_too_low(self):
        jd = parse_jd("工作地点:北京 薪资:30-50K 大专 3-5年 Python", plus_skills=[])
        r = make_scorer().score(jd)
        assert not r.passed
        assert any("学历" in x for x in r.reasons)


# ---------- 软性评分 ----------

class TestSoftScore:
    def test_good_job_passes_and_grades(self):
        jd = parse_jd(
            "岗位:高级后端工程师 工作地点:北京 薪资:30-50K 本科 3-5年 "
            "精通Python、FastAPI、Redis,有高并发经验,公司已融资",
            plus_skills=["FastAPI", "Redis", "高并发"],
        )
        r = make_scorer().score(jd)
        assert r.passed
        assert r.total >= 55
        assert r.grade in ("S", "A", "B")

    def test_skill_score_weighted(self):
        jd = parse_jd("精通 FastAPI", plus_skills=["FastAPI", "Redis", "高并发"])
        s = make_scorer()
        score = s._skill_score(jd)
        assert score > 0
        assert score <= 100
