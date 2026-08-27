"""打招呼语生成器:基于个人画像 + 岗位匹配点,生成个性化打招呼语。

BOSS直聘是「聊」平台,投递 = 发打招呼语。个性化招呼比「您好,看到贵司招聘」
回复率高得多。这里把画像(config/profile.yaml 的 personal 段)和岗位匹配技能
拼成一段简洁、有卖点的招呼。
"""
from __future__ import annotations


def generate_greeting(profile: dict, job: dict) -> str:
    """根据画像与岗位生成打招呼语。

    Args:
        profile: 画像配置(含 personal 段)。
        job: 岗位 dict(含 title/company/details.skill_hits)。
    Returns:
        一段可直接复制发送的打招呼语。
    """
    personal = profile.get("personal", {}) or {}
    name = personal.get("name", "")
    headline = personal.get("headline", "")
    highlights = personal.get("highlights", []) or []

    title = (job.get("title") or "该").strip()
    company = (job.get("company") or "").strip()

    # 匹配技能(优先取 details.skill_hits,退回 skills 字段)
    hits = []
    details = job.get("details") or {}
    if isinstance(details, dict) and details.get("skill_hits"):
        hits = details["skill_hits"]
    elif job.get("skills"):
        hits = job["skills"]
    # 排除泛化词,只留硬技能/具体词
    generic = {"数据分析", "报告", "客户沟通", "商业分析", "指标体系", "数据产品"}
    hits = [h for h in hits if h not in generic][:4]

    parts: list[str] = []
    # 开头:自我介绍
    intro = f"您好，我是{name}"
    if headline:
        intro += f"，{headline}"
    parts.append(intro + "。")

    # 匹配点
    if title or company:
        target = f"「{title}」" + (f"（{company}）" if company else "")
        if hits:
            parts.append(f"看到贵司{target}岗位，我的 {('、'.join(hits))} 经验与要求高度匹配。")
        else:
            parts.append(f"看到贵司{target}岗位，非常感兴趣。")

    # 亮点(取第一条最硬的)
    if highlights:
        parts.append(highlights[0] + "。")

    parts.append("期待进一步沟通，谢谢！")
    return "".join(parts)


def greeting_from_profile_and_job(profile: dict, job: dict) -> str:
    """别名,保持与旧调用兼容。"""
    return generate_greeting(profile, job)
