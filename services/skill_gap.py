"""技能差距分析服务 —— 对比用户技能与市场需求"""
import re
from tools.skill_guard import normalize_job_name, ALIASES
from memory.long_term import query_skill_rank
from core.logger import get_logger

logger = get_logger(__name__)

# 过宽泛的领域大类词（单独出现无技能指向性）
_BROAD_TERMS = {
    "ai", "iot", "nlp", "api", "net", "orm", "sql",
    "人工智能", "深度学习", "机器学习", "自然语言", "自然语言处理",
    "计算机科学", "软件工程", "信息技术", "大数据",
    "前端", "后端", "服务端", "全栈", "算法", "测试", "运维",
    "标注", "清洗", "维护", "编码", "调试", "重构", "辅导", "评测",
    "跨平台", "高性能", "高并发", "硬件设计", "软件代码",
}

# 动词/动作词（不是技能名）
_VERBS = {
    "清洗", "重构", "辅导", "测试", "评审", "评估", "审核", "调研",
    "排查", "部署", "迁移", "对接", "封装", "拆解",
}


def is_low_quality_skill(skill: str) -> bool:
    """判断技能是否为低质量泛词"""
    if not isinstance(skill, str):
        return True
    s = skill.strip()
    if not s:
        return True
    lower = s.lower()

    # 过短（1-2 个字符且不是已知缩写）
    if len(lower) <= 2 and lower not in {"go", "c+", "ai"}:
        return True

    # 过宽泛领域词
    if lower in _BROAD_TERMS or s in _BROAD_TERMS:
        return True

    # 纯动词
    if s in _VERBS:
        return True

    # 以"开发"结尾且长度 ≤6（如"后端开发"、"前端开发"是岗位不是技能）
    if re.match(r"^.{0,4}(开发|工程师|岗位|实习)$", s):
        return True

    return False


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

    # 获取市场技能排名（多取一些，过滤后可能减少）
    raw_market = query_skill_rank(job_name, top_n=min(top_n * 2, 50))
    if not raw_market:
        return {
            "job_name": job_name,
            "market_skills": [],
            "matched_skills": [],
            "missing_skills": [],
            "coverage_ratio": 0.0,
            "priority_order": [],
            "confidence": "none",
            "summary": f"暂无「{job_name}」的市场技能数据，请先在对话中分析该岗位。",
        }

    # 过滤低质量技能
    market = [item for item in raw_market if not is_low_quality_skill(item["skill"])]
    filtered_count = len(raw_market) - len(market)
    market = market[:top_n]  # 截取 top_n

    # 置信度评估
    total_jds = market[0].get("total_jds", 0) if market else 0
    if len(market) < 5:
        confidence = "low"
    elif total_jds < 5:
        confidence = "low"
    elif filtered_count > len(raw_market) * 0.3:
        confidence = "medium"
    else:
        confidence = "high"

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
    if confidence == "low":
        summary_parts.append("（当前数据样本较少，结果仅供参考）")
    summary = "".join(summary_parts)

    logger.info(
        f"技能差距分析: {job_name} | 市场{market_count} | 匹配{matched_count} | "
        f"缺口{len(missing)} | 覆盖率{coverage_ratio:.0%} | 置信{confidence} | 过滤{filtered_count}"
    )

    return {
        "job_name": job_name,
        "market_skills": market,
        "matched_skills": matched,
        "missing_skills": missing,
        "coverage_ratio": coverage_ratio,
        "priority_order": priority_order,
        "confidence": confidence,
        "summary": summary,
    }
