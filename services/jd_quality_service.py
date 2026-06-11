"""JD 质量过滤与去重服务 — v0.15"""
from __future__ import annotations
import re
from tools.skill_guard import normalize_job_name
from core.logger import get_logger

logger = get_logger(__name__)

MIN_TEXT_LENGTH = 100
MAX_TEXT_LENGTH = 8000

# 岗位关键词（JD 中必须至少出现一个才算相关）
JOB_KEYWORDS = (
    "岗位", "职责", "要求", "任职", "招聘", "职位", "工作内容",
    "job", "requirement", "responsibility", "qualification",
    "任职要求", "岗位职责", "工作职责", "岗位要求", "职位描述",
)

# 福利/广告关键词（占比过高则降权）
WELFARE_KEYWORDS = (
    "五险一金", "年终奖", "带薪年假", "节日福利", "团建",
    "下午茶", "零食", "健身房", "班车", "加班补贴",
    "股票期权", "扁平管理", "弹性工作",
)

# 公司介绍关键词（占比过高则降权）
COMPANY_KEYWORDS = (
    "公司简介", "关于我们", "企业文化", "公司成立于",
    "公司规模", "融资", "上市", "行业领先", "核心业务",
)

# 纯广告/推广关键词
AD_KEYWORDS = (
    "点击申请", "立即投递", "扫码报名", "限时优惠",
    "免费试听", "报名链接", "课程介绍", "培训",
)

JOB_TITLE_PATTERN = re.compile(
    r"(实习|intern|校招|社招|应届|工程师|开发|经理|分析师|设计师|测试|运维|算法|产品)",
    re.I,
)


def judge_jd_quality(jd_text: str, job_name: str = "") -> dict:
    """
    判断单条 JD 的质量。

    Returns:
        {
            "is_valid": bool,
            "quality_score": 0-100,
            "quality_level": "high"/"medium"/"low",
            "quality_reasons": list[str],
        }
    """
    text = (jd_text or "").strip()
    reasons = []

    # 1. 空文本
    if not text:
        return {"is_valid": False, "quality_score": 0, "quality_level": "low", "quality_reasons": ["文本为空"]}

    # 2. 过短
    if len(text) < MIN_TEXT_LENGTH:
        return {"is_valid": False, "quality_score": 10, "quality_level": "low", "quality_reasons": ["文本过短"]}

    # 3. 过长（可能是整页 HTML 或多条 JD 混在一起）
    if len(text) > MAX_TEXT_LENGTH:
        reasons.append("文本过长，可能包含多条 JD")
        score = 50
    else:
        score = 70  # 基础分

    text_lower = text.lower()

    # 4. 缺少岗位关键词（纯广告/纯介绍）
    has_job_keyword = any(k in text_lower for k in JOB_KEYWORDS)
    if not has_job_keyword:
        return {"is_valid": False, "quality_score": 20, "quality_level": "low", "quality_reasons": ["缺少岗位/职责/要求关键词"]}

    # 5. 纯广告
    ad_hits = sum(1 for k in AD_KEYWORDS if k in text_lower)
    if ad_hits >= 3:
        return {"is_valid": False, "quality_score": 15, "quality_level": "low", "quality_reasons": ["疑似广告/推广内容"]}

    # 6. 岗位相关性（如果有 job_name）
    if job_name:
        job_lower = normalize_job_name(job_name).lower()
        # 检查 JD 中是否包含岗位名或相关词
        job_words = set(re.findall(r'[一-鿿]{2,}|[a-zA-Z]+', job_lower))
        jd_words = set(re.findall(r'[一-鿿]{2,}|[a-zA-Z]+', text_lower))
        overlap = job_words & jd_words
        if not overlap and not any(w in text_lower for w in job_lower.split()):
            reasons.append(f"JD 可能与岗位「{job_name}」不相关")
            score -= 20

    # 7. 福利/公司介绍占比过高
    welfare_hits = sum(1 for k in WELFARE_KEYWORDS if k in text_lower)
    company_hits = sum(1 for k in COMPANY_KEYWORDS if k in text_lower)
    if welfare_hits >= 5:
        reasons.append("福利描述过多，技术要求偏少")
        score -= 10
    if company_hits >= 3:
        reasons.append("公司介绍偏多")
        score -= 5

    # 8. 有技术要求加分
    tech_keywords = ("熟悉", "掌握", "精通", "了解", "使用", "开发", "经验")
    tech_hits = sum(1 for k in tech_keywords if k in text_lower)
    if tech_hits >= 3:
        score += 15
    elif tech_hits >= 1:
        score += 5

    # 9. 有学历/经验要求加分
    if any(k in text_lower for k in ("本科", "硕士", "博士", "大专", "学历")):
        score += 5
    if any(k in text_lower for k in ("年经验", "年以上", "工作经验", "实习")):
        score += 5

    # 10. 有职责描述加分
    if any(k in text_lower for k in ("负责", "参与", "主导", "完成", "承担")):
        score += 5

    score = max(0, min(100, score))

    if score >= 70:
        level = "high"
    elif score >= 50:
        level = "medium"
    else:
        level = "low"

    is_valid = score >= 40
    if not is_valid:
        reasons.append("综合评分过低")

    return {
        "is_valid": is_valid,
        "quality_score": score,
        "quality_level": level,
        "quality_reasons": reasons,
    }


def filter_jd_items(jd_items: list[dict], job_name: str = "") -> tuple[list[dict], list[dict], dict]:
    """
    过滤 JD 列表，返回 (valid_jds, filtered_jds, summary)。

    Args:
        jd_items: [{"text": ..., "title": ..., "company": ..., ...}, ...]
        job_name: 目标岗位名，用于相关性判断

    Returns:
        (valid_jds, filtered_jds, {"total": N, "valid": N, "filtered": N, "quality_summary": {...}})
    """
    valid = []
    filtered = []
    seen_hashes = set()
    quality_scores = []

    for item in jd_items:
        text = (item.get("text") or item.get("content") or "").strip()

        # 精确去重
        import hashlib
        text_hash = hashlib.sha256(text[:500].encode("utf-8")).hexdigest()
        if text_hash in seen_hashes:
            filtered.append({**item, "filter_reason": "重复内容"})
            continue
        seen_hashes.add(text_hash)

        # 质量判断
        quality = judge_jd_quality(text, job_name=job_name)
        quality_scores.append(quality["quality_score"])

        if quality["is_valid"]:
            valid.append({**item, "quality_score": quality["quality_score"], "quality_level": quality["quality_level"]})
        else:
            filtered.append({**item, "filter_reason": "; ".join(quality["quality_reasons"])})

    avg_score = round(sum(quality_scores) / max(1, len(quality_scores)), 1) if quality_scores else 0
    high_count = sum(1 for q in quality_scores if q >= 70)

    summary = {
        "total": len(jd_items),
        "valid": len(valid),
        "filtered": len(filtered),
        "avg_quality_score": avg_score,
        "high_quality_count": high_count,
    }

    logger.info(f"JD 质量过滤: {len(jd_items)} 条 → 有效 {len(valid)} 条，过滤 {len(filtered)} 条，平均质量 {avg_score}")
    return valid, filtered, summary
