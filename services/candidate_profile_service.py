"""Candidate profile extraction service — v0.9"""
from __future__ import annotations
import json
import re
from datetime import datetime
from services.screening import (
    _extract_candidate_education, _extract_candidate_experience,
    _estimate_experience_years, _detect_sensitive_info,
    _split_sentences, MAJOR_HINTS,
)
from services.profile_schemas import CandidateProfileResult, EvidenceItem
from core.logger import get_logger

logger = get_logger(__name__)


def _extract_projects(text_value: str) -> list[dict]:
    """提取项目经历，区分 explicit/inferred"""
    sentences = _split_sentences(text_value)
    projects = []
    current = []
    for s in sentences:
        if any(k in s for k in ("项目", "平台", "系统", "产品", "工具", "网站")):
            current.append(s)
        elif current:
            projects.append(" ".join(current)[:200])
            current = []
    if current:
        projects.append(" ".join(current)[:200])
    return [{"name": p[:30], "description": p, "confidence": "explicit"} for p in projects[:6]]


def _extract_achievements(text_value: str) -> list[dict]:
    """提取成果证据"""
    achievements = []
    for s in _split_sentences(text_value):
        if re.search(r"\d+[%万千]|提升|降低|优化|上线|获奖|竞赛|专利|论文", s):
            achievements.append({
                "description": s[:150],
                "has_metric": bool(re.search(r"\d+[%万千]", s)),
            })
    return achievements[:8]


def _extract_learning_signals(text_value: str) -> list[str]:
    """提取学习能力信号"""
    signals = []
    patterns = [
        (r"(自学|自研|独立学习)", "自主学习"),
        (r"(开源|github|贡献)", "开源参与"),
        (r"(竞赛|比赛|hackathon)", "竞赛经历"),
        (r"(论文|专利|博客|技术文章)", "技术输出"),
        (r"(证书|认证|考取)", "认证获取"),
        (r"(新技术|新框架|快速上手)", "技术迁移"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, text_value, re.I):
            signals.append(label)
    return signals


def _extract_business_understanding(text_value: str) -> list[str]:
    """提取业务理解信号"""
    domains = []
    domain_keywords = {
        "电商": ("电商", "商城", "购物", "下单"),
        "金融": ("金融", "支付", "风控", "交易"),
        "教育": ("教育", "在线学习", "课程"),
        "医疗": ("医疗", "健康", "医院"),
        "游戏": ("游戏", "引擎", "Unity"),
        "社交": ("社交", "IM", "消息"),
        "企业服务": ("SaaS", "CRM", "ERP", "OA"),
    }
    for domain, keywords in domain_keywords.items():
        if any(k in text_value for k in keywords):
            domains.append(domain)
    return domains


def _extract_collaboration_signals(text_value: str) -> list[str]:
    """提取协作信号"""
    signals = []
    patterns = [
        (r"(团队|协作|配合|跨部门)", "团队协作"),
        (r"(沟通|表达|汇报|演示", "沟通表达"),
        (r"(带领|负责|leader|lead", "领导力"),
        (r"(Code Review|代码评审|技术分享)", "技术分享"),
    ]
    for pattern, label in patterns:
        try:
            if re.search(pattern, text_value, re.I):
                signals.append(label)
        except Exception:
            pass
    return signals


def extract_candidate_profile(
    resume_text: str = "",
    user_id: int = 0,
    resume_filename: str = "",
    conversation_text: str = "",
) -> CandidateProfileResult:
    """从简历文本中提取结构化候选人画像"""
    text_value = (resume_text or "").strip()
    if conversation_text:
        text_value += "\n" + conversation_text

    education = _extract_candidate_education(text_value)
    exp = _extract_candidate_experience(text_value)
    projects = _extract_projects(text_value)
    achievements = _extract_achievements(text_value)
    learning = _extract_learning_signals(text_value)
    business = _extract_business_understanding(text_value)
    collab = _extract_collaboration_signals(text_value)
    sensitive = _detect_sensitive_info(text_value)

    # 技能栈
    from services.resume_profile import extract_profile_from_text, profile_to_skill_names
    base = extract_profile_from_text(text_value, use_llm=True) if text_value else {"skills": [], "summary": "", "parser": "empty"}
    skill_stack = []
    for item in base.get("skills", []):
        name = item if isinstance(item, str) else item.get("skill", "")
        conf = "explicit" if isinstance(item, dict) and item.get("confidence", 0) >= 0.7 else "inferred"
        skill_stack.append({"skill": str(name), "confidence": conf})

    # 经历年限
    exp_years = _estimate_experience_years(text_value)

    # 风险点
    risks = []
    if not education.get("degree"):
        risks.append("未明确学历")
    if not exp.get("has_project") and not exp.get("has_internship"):
        risks.append("缺少项目/实习经历")
    if not achievements:
        risks.append("缺少量化成果")

    # 置信度
    conf = "high" if (skill_stack and projects and education.get("degree")) else "medium" if skill_stack else "low"

    # 证据
    evidence = []
    if text_value:
        evidence.append(EvidenceItem(text=text_value[:200], source="简历原文"))

    return CandidateProfileResult(
        education_background={
            "degree": education.get("degree", ""),
            "major": education.get("major", ""),
            "graduation_year": education.get("graduation_year", ""),
            "school": education.get("school_evidence", [""])[0] if education.get("school_evidence") else "",
        },
        skill_stack=skill_stack,
        projects=projects,
        internships=[{"description": s, "confidence": "explicit"} for s in exp.get("internships", [])],
        work_experiences=[{"description": s, "confidence": "explicit"} for s in exp.get("work_experience", [])],
        business_understanding=business,
        achievements=achievements,
        learning_signals=learning,
        transferable_strengths=collab,
        collaboration_signals=collab,
        risk_points=risks,
        evidence=evidence,
        confidence=conf,
        sensitive_detected=sensitive,
        summary=base.get("summary") or f"识别到 {len(skill_stack)} 个技能、{len(projects)} 个项目经历。",
    )


def save_candidate_profile(profile: CandidateProfileResult, user_id: int, resume_filename: str = "") -> int:
    """保存候选人画像到数据库"""
    from models.database import SessionLocal
    from models.profile import CandidateProfile
    with SessionLocal() as session:
        obj = CandidateProfile(
            user_id=user_id,
            source_type="resume_text",
            resume_filename=resume_filename,
            raw_text="",
            education_background=json.dumps(profile.education_background, ensure_ascii=False),
            skill_stack=json.dumps(profile.skill_stack, ensure_ascii=False),
            projects=json.dumps(profile.projects, ensure_ascii=False),
            internships=json.dumps(profile.internships, ensure_ascii=False),
            work_experiences=json.dumps(profile.work_experiences, ensure_ascii=False),
            business_understanding=json.dumps(profile.business_understanding, ensure_ascii=False),
            achievements=json.dumps(profile.achievements, ensure_ascii=False),
            learning_signals=json.dumps(profile.learning_signals, ensure_ascii=False),
            transferable_strengths=json.dumps(profile.transferable_strengths, ensure_ascii=False),
            collaboration_signals=json.dumps(profile.collaboration_signals, ensure_ascii=False),
            risk_points=json.dumps(profile.risk_points, ensure_ascii=False),
            evidence=json.dumps([e.model_dump() for e in profile.evidence], ensure_ascii=False),
            confidence=profile.confidence,
            sensitive_detected=json.dumps(profile.sensitive_detected, ensure_ascii=False),
        )
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.id
