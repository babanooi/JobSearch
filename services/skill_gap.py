"""技能差距分析服务 —— 对比用户技能与市场需求"""
from tools.skill_guard import normalize_job_name, ALIASES
from memory.long_term import query_skill_rank
from core.logger import get_logger

logger = get_logger(__name__)


def _normalize_skill(skill) -> str:
    """归一化技能名：防御 None/非字符串 + strip + 别名表 + 首字母大写"""
    if not isinstance(skill, str):
        return ""
    s = skill.strip()
    if not s:
        return ""
    lower = s.lower()
    if lower in ALIASES:
        return ALIASES[lower]
    return s


def analyze_skill_gap(
    job_name: str,
    user_skills: list[str],
    top_n: int = 15,
) -> dict:
    """
    技能差距分析。

    Args:
        job_name: 目标岗位名
        user_skills: 用户已掌握的技能列表（None 视为空列表）
        top_n: 取市场 Top N 热门技能

    Returns:
        {
            "job_name": str,
            "market_skills": [{"skill": str, "count": int, "total_jds": int}, ...],
            "matched_skills": [{"skill": str, "count": int, "total_jds": int}, ...],
            "missing_skills": [{"skill": str, "count": int, "total_jds": int}, ...],
            "coverage_ratio": float,
            "priority_order": [str, ...],
            "summary": str,
        }
    """
    # 兼容 None + 去重
    if user_skills is None:
        user_skills = []

    # 限制 top_n 到 1-50，避免直接调用时异常
    top_n = max(1, min(top_n, 50))

    # 归一化岗位名
    job_name = normalize_job_name(job_name)

    # 获取市场技能排名
    market = query_skill_rank(job_name, top_n=top_n)
    if not market:
        return {
            "job_name": job_name,
            "market_skills": [],
            "matched_skills": [],
            "missing_skills": [],
            "coverage_ratio": 0.0,
            "priority_order": [],
            "summary": f"暂无「{job_name}」的市场技能数据，请先在对话中分析该岗位。",
        }

    # 归一化用户技能并匹配
    user_normalized = set()
    for s in user_skills:
        ns = _normalize_skill(s)
        if ns:
            user_normalized.add(ns.lower())

    matched = []
    missing = []
    for item in market:
        normalized = _normalize_skill(item["skill"]).lower()
        if normalized in user_normalized:
            matched.append(item)  # 返回对象而非字符串
        else:
            missing.append(item)

    # 缺口技能按 count 降序
    missing.sort(key=lambda x: x.get("count", 0), reverse=True)

    # 覆盖率（用 set 去重后的匹配数，避免重复技能重复计数）
    market_count = len(market)
    matched_count = len(matched)
    coverage_ratio = round(matched_count / market_count, 4) if market_count > 0 else 0.0

    # 学习优先级：缺口技能前 5 个
    priority_order = [item["skill"] for item in missing[:5]]

    # 摘要
    summary_parts = [
        f"「{job_name}」市场 Top{market_count} 技能中，",
        f"你已掌握 {matched_count} 个（覆盖率 {coverage_ratio:.0%}），",
        f"缺口 {len(missing)} 个。",
    ]
    if priority_order:
        summary_parts.append(f"建议优先学习：{'、'.join(priority_order)}。")
    summary = "".join(summary_parts)

    logger.info(
        f"技能差距分析: {job_name} | 市场{market_count} | 匹配{matched_count} | "
        f"缺口{len(missing)} | 覆盖率{coverage_ratio:.0%}"
    )

    return {
        "job_name": job_name,
        "market_skills": market,
        "matched_skills": matched,
        "missing_skills": missing,
        "coverage_ratio": coverage_ratio,
        "priority_order": priority_order,
        "summary": summary,
    }
