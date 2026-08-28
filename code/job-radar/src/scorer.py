"""打分引擎:硬性过滤(一票否决) + 软性评分(加权) → S/A/B/C 分级。

所有参数来自画像配置(config/profile.yaml),与解析结果解耦。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from .parser import ParsedJD


@dataclass
class ScoreResult:
    """一次打分的结果。"""

    total: float = 0.0
    grade: str = "C"
    passed: bool = False
    reasons: list[str] = field(default_factory=list)  # 硬性过滤未通过原因
    details: dict = field(default_factory=dict)  # 各维度得分明细

    def to_dict(self) -> dict:
        return asdict(self)


class Scorer:
    """基于画像配置的 JD 打分器。"""

    def __init__(self, profile: dict):
        self.profile = profile
        self.weights = profile.get("weights", {})
        self.grades = profile.get("grades", {"S": 85, "A": 70, "B": 55, "C": 0})

    # ---------- 硬性过滤 ----------

    def _hard_filter(self, jd: ParsedJD) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        passed = True

        # 城市
        cities = self.profile.get("cities", [])
        if cities and jd.city and jd.city not in cities:
            reasons.append(f"城市不符:{jd.city} ∉ {cities}")
            passed = False
        # 注意:城市解析不到(jd.city == "")时不否决,留给软性分处理

        # 薪资下限
        salary_min = self.profile.get("salary_min", 0)
        if salary_min and jd.salary_min and jd.salary_min < salary_min:
            reasons.append(f"薪资过低:{jd.salary_min} < {salary_min}")
            passed = False

        # 经验区间
        exp = self.profile.get("experience", {})
        exp_min_want, exp_max_want = exp.get("min", 0), exp.get("max", 0)
        if exp_max_want and jd.experience_min and jd.experience_min > exp_max_want:
            reasons.append(f"经验要求过高:{jd.experience_min}年 > {exp_max_want}年")
            passed = False
        if exp_min_want and jd.experience_max and jd.experience_max < exp_min_want:
            reasons.append(f"经验要求过低:{jd.experience_max}年 < {exp_min_want}年")
            passed = False

        # 学历
        want_edu = self.profile.get("education", "")
        edu_rank = {"大专": 1, "专科": 1, "本科": 2, "硕士": 3, "博士": 4}
        if want_edu and jd.education:
            if edu_rank.get(jd.education, 0) < edu_rank.get(want_edu, 0):
                reasons.append(f"学历不符:{jd.education} < {want_edu}")
                passed = False

        # 必须技能(至少命中 1 个)
        must = self.profile.get("must_skills", [])
        if must:
            text_lower = jd.raw.lower()
            hit = [s for s in must if s.lower() in text_lower]
            if not hit:
                reasons.append(f"未命中必须技能:{must}")
                passed = False

        return passed, reasons

    # ---------- 软性评分 ----------

    def _skill_score(self, jd: ParsedJD) -> float:
        """技能匹配度:基于命中技能的加权分,按命中数量与权重综合。

        算法:命中加权分 hit_weight 与命中数量都参与——
        - 命中的技能越多、权重越高,分数越高;
        - 满分条件:命中核心权重(前若干技能)或命中 5+ 个技能。
        """
        plus = self.profile.get("plus_skills", [])
        # 按权重从高到低排序,取前 N 个视为「核心技能」
        ordered = sorted(plus, key=lambda p: -p.get("weight", 0))
        core_weight = sum(p.get("weight", 0) for p in ordered[:8]) or 1
        hit_weight = 0.0
        hit_count = 0
        for p in plus:
            if p["name"].lower() in jd.raw.lower():
                hit_weight += p.get("weight", 0)
                hit_count += 1
        # 命中数贡献:0→0, 1→30, 2→50, 3→65, 4→78, 5+→90
        count_score = {0: 0, 1: 30, 2: 50, 3: 65, 4: 78}.get(hit_count, 90)
        # 权重贡献:命中核心权重占比
        weight_score = min(100, hit_weight / core_weight * 100)
        return round(max(count_score, weight_score), 1)

    def _experience_score(self, jd: ParsedJD) -> float:
        """经验契合:JD 要求的年限区间落在画像期望区间内 → 满分。"""
        exp = self.profile.get("experience", {})
        want_min, want_max = exp.get("min", 0), exp.get("max", 0)
        if not want_max:
            return 100.0
        if jd.experience_min == 0 and jd.experience_max == 0:
            return 100.0  # 未标注经验要求,视为不限
        jd_min = jd.experience_min
        jd_max = jd.experience_max or want_max
        # 重叠程度
        overlap_lo = max(jd_min, want_min)
        overlap_hi = min(jd_max, want_max)
        if overlap_hi < overlap_lo:
            return 30.0
        span = max(jd_max - jd_min, 1)
        return round(min(100, (overlap_hi - overlap_lo + 1) / span * 100), 1)

    def _company_score(self, jd: ParsedJD) -> float:
        """公司实力:命中融资/规模关键词加分。"""
        keywords = self.profile.get("company_plus", [])
        hits = sum(1 for k in keywords if k in jd.raw)
        return round(min(100, hits * 25), 1)

    def _freshness_score(self, jd: ParsedJD) -> float:
        """新鲜度:发布时间越近越高。无法解析时给 70(中性)。"""
        pub = jd.published
        if not pub:
            return 70.0
        if "天前" in pub or "小时内" in pub or "小时前" in pub or "分钟前" in pub:
            import re

            m = re.search(r"(\d+)\s*(天|小时|分钟)", pub)
            if m:
                n, unit = int(m.group(1)), m.group(2)
                factor = {"分钟": 1 / 1440, "小时": 1 / 24, "天": 1}[unit]
                days = n * factor
                return round(max(0, 100 - days * 10), 1)
        return 70.0

    def _commute_score(self, jd: ParsedJD) -> float:
        """通勤/城市:在目标城市列表得满分。"""
        cities = self.profile.get("cities", [])
        if jd.city in cities:
            return 100.0
        return 50.0

    def _other_score(self, jd: ParsedJD) -> float:
        """其他:福利关键词加分。"""
        keywords = self.profile.get("benefit_plus", [])
        hits = sum(1 for k in keywords if k in jd.raw)
        return round(min(100, hits * 20), 1)

    # ---------- 总打分 ----------

    def score(self, jd: ParsedJD) -> ScoreResult:
        passed, reasons = self._hard_filter(jd)
        if not passed:
            return ScoreResult(passed=False, reasons=reasons, grade="C")

        dims = {
            "skill": self._skill_score(jd),
            "experience": self._experience_score(jd),
            "company": self._company_score(jd),
            "freshness": self._freshness_score(jd),
            "commute": self._commute_score(jd),
            "other": self._other_score(jd),
        }
        plus = self.profile.get("plus_skills", [])
        skill_hits = [p["name"] for p in plus if p["name"].lower() in jd.raw.lower()]
        total = sum(
            dims[k] * self.weights.get(k, 0) / 100 for k in dims
        )
        total = round(total, 1)

        grade = "C"
        for g in ["S", "A", "B", "C"]:
            if total >= self.grades.get(g, 0):
                grade = g
                break

        return ScoreResult(
            total=total, grade=grade, passed=True,
            details={**dims, "skill_hits": skill_hits},
        )


def grade_label(grade: str) -> str:
    return {
        "S": "强匹配 · 立即投",
        "A": "可投",
        "B": "观察",
        "C": "放弃",
    }.get(grade, grade)
