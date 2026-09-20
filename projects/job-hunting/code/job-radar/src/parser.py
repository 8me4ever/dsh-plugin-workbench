"""JD 解析器:从非结构化 JD 文本中抽取结构化字段。

V0 用正则 + 关键词规则实现,不依赖 LLM,可离线运行、逻辑透明。
V1 之后可无缝替换为 LLM 解析(接口保持一致即可)。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict


@dataclass
class ParsedJD:
    """解析出的结构化 JD 字段。"""

    title: str = ""
    company: str = ""
    city: str = ""
    salary_min: int = 0  # 月薪下限(元)
    salary_max: int = 0  # 月薪上限(元)
    experience_min: int = 0  # 要求经验下限(年)
    experience_max: int = 0  # 要求经验上限(年),0 表示不限
    experience_text: str = ""
    education: str = ""  # 最低学历要求
    skills: list[str] = field(default_factory=list)  # 命中的技能关键词
    url: str = ""
    published: str = ""  # 原始发布时间文本
    raw: str = ""  # 原始 JD 全文

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------- 正则规则 ----------

# 薪资:美元年薪模式(带 $ 前缀,命中按 USD→CNY 换算;优先匹配,避免 "1-3 days, $1-3K" 干扰)
_SALARY_USD_PATTERNS = [
    re.compile(r"\$\s*(\d{1,3}(?:\.\d)?)\s*[kK]\s*[-~—–]\s*\$?\s*(\d{1,3}(?:\.\d)?)\s*[kK]"),
    re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+)\s*[-~—–]\s*\$?\s*(\d{1,3}(?:,\d{3})+)"),
]
# 薪资:人民币模式 15-25K / 15k-25k / 15-25千 / 2-3万 / 月薪15-25k
_SALARY_CNY_PATTERNS = [
    re.compile(r"(\d{1,3}(?:\.\d)?)\s*[-~—–]\s*(\d{1,3}(?:\.\d)?)\s*[kK千]"),
    re.compile(r"(\d{1,2}(?:\.\d)?)\s*[-~—–]\s*(\d{1,2}(?:\.\d)?)\s*万"),
    re.compile(r"月薪\s*(\d{1,3}(?:\.\d)?)\s*[-~—–]\s*(\d{1,3}(?:\.\d)?)\s*[kK千]"),
]

# 汇率:1 USD ≈ 7.2 CNY(可调)
USD_TO_CNY = 7.2

# 经验:3-5年 / 3年以上 / 5年以下 / 经验不限 / 1年及以下
_EXP_PATTERNS = [
    re.compile(r"(\d{1,2})\s*[-~—–]\s*(\d{1,2})\s*年"),
    re.compile(r"(\d{1,2})\s*年\s*以上"),
    re.compile(r"(\d{1,2})\s*年\s*以下"),
    re.compile(r"经验不限|不限经验|应届"),
]

# 学历:大专/本科/硕士/博士/研究生
_EDU_PATTERNS = [
    re.compile(r"(博士|硕士|研究生|本科|大专|专科|高中)"),
]

# 城市(常见城市列表,可扩展)
_CITY_KEYWORDS = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "苏州",
    "西安", "长沙", "重庆", "天津", "郑州", "青岛", "厦门", "合肥", "东莞",
    "佛山", "宁波", "无锡", "福州", "济南", "大连", "沈阳", "昆明", "远程",
]

# 发布/标题/公司关键词
_PUBLISH_PATTERNS = [
    re.compile(r"(?:发布于|发布时间|更新于)?\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})"),
    re.compile(r"(\d+)\s*(?:天|小时|分钟)\s*(?:前|以内)"),
]

_TITLE_PATTERNS = [
    re.compile(r"岗位(?:名称|名|标题)?\s*[:：]\s*([^\n\r,，。]+)"),
    re.compile(r"职位(?:名称|名|标题)?\s*[:：]\s*([^\n\r,，。]+)"),
    re.compile(r"招聘\s*[:：]\s*([^\n\r,，。]+)"),
]

_COMPANY_PATTERNS = [
    re.compile(r"公司(?:名称|名)?\s*[:：]\s*([^\n\r,，。]+)"),
    re.compile(r"企业(?:名称|名)?\s*[:：]\s*([^\n\r,，。]+)"),
]


def _parse_salary(text: str) -> tuple[int, int]:
    """返回 (salary_min, salary_max),单位元;解析不到返回 (0, 0)。"""
    # 美元年薪优先(更强信号)
    for pat in _SALARY_USD_PATTERNS:
        m = pat.search(text)
        if m:
            lo = float(m.group(1).replace(",", ""))
            hi = float(m.group(2).replace(",", ""))
            # 美元年薪 → 人民币月薪(年薪/12)
            return int(lo * 1000 * USD_TO_CNY / 12), int(hi * 1000 * USD_TO_CNY / 12)
    # 人民币月薪
    for pat in _SALARY_CNY_PATTERNS:
        m = pat.search(text)
        if m:
            lo, hi = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
            if "万" in m.group(0):
                lo, hi = lo * 10000, hi * 10000
            else:
                lo, hi = lo * 1000, hi * 1000
            return int(lo), int(hi)
    return 0, 0


def _parse_experience(text: str) -> tuple[int, int, str]:
    """返回 (exp_min, exp_max, text);exp_max=0 表示不限。"""
    for pat in _EXP_PATTERNS:
        m = pat.search(text)
        if m:
            matched = m.group(0)
            if "以上" in matched:
                n = int(m.group(1))
                return n, 0, matched
            if "以下" in matched:
                n = int(m.group(1))
                return 0, n, matched
            if "不限" in matched or "应届" in matched:
                return 0, 0, matched
            return int(m.group(1)), int(m.group(2)), matched
    return 0, 0, ""


def _parse_education(text: str) -> str:
    for pat in _EDU_PATTERNS:
        m = pat.search(text)
        if m:
            # 统一口径
            return {"研究生": "硕士"}.get(m.group(1), m.group(1))
    return ""


def _parse_city(text: str) -> str:
    for city in _CITY_KEYWORDS:
        if city in text:
            return city
    return ""


def _parse_published(text: str) -> str:
    for pat in _PUBLISH_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)
    return ""


def _extract_field(text: str, patterns: list[re.Pattern]) -> str:
    """从文本中提取字段(取第一个命中的完整行内容)。"""
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return ""


def parse_jd(
    text: str,
    plus_skills: list[str] | None = None,
    title: str = "",
    company: str = "",
    url: str = "",
) -> ParsedJD:
    """从 JD 全文解析结构化字段。

    Args:
        text: JD 全文(标题+正文)。
        plus_skills: 用于在文本中命中的技能关键词列表(通常来自画像配置)。
        title/company/url: 元信息,抓取源可传入。
    """
    if plus_skills is None:
        plus_skills = []

    salary_min, salary_max = _parse_salary(text)
    exp_min, exp_max, exp_text = _parse_experience(text)
    education = _parse_education(text)
    city = _parse_city(text)

    # 标题/公司:优先用调用方传入值,否则从 JD 文本提取
    if not title:
        title = _extract_field(text, _TITLE_PATTERNS)
    if not company:
        company = _extract_field(text, _COMPANY_PATTERNS)

    # 技能命中:大小写不敏感
    text_lower = text.lower()
    skills = [
        s for s in plus_skills if s.lower() in text_lower
    ]

    return ParsedJD(
        title=title,
        company=company,
        city=city,
        salary_min=salary_min,
        salary_max=salary_max,
        experience_min=exp_min,
        experience_max=exp_max,
        experience_text=exp_text,
        education=education,
        skills=skills,
        url=url,
        published=_parse_published(text),
        raw=text,
    )
