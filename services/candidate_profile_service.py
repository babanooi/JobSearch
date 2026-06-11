"""Candidate profile extraction service — v0.19 增强规则兜底"""
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
from tools.skill_guard import ALIASES
from core.logger import get_logger

logger = get_logger(__name__)

# 技能提取停用词
_SKILL_STOP = {
    "熟悉", "掌握", "了解", "精通", "具备", "使用", "具有", "会",
    "以上", "优先", "经验", "能力", "技术", "开发", "工程师",
    "相关", "学历", "专业", "本科", "硕士", "博士", "大专",
    "年以上", "应届", "实习", "工作", "岗位", "职责", "要求",
    "负责", "参与", "承担", "主导", "完成", "推动", "设计",
    "维护", "优化", "上线", "部署", "测试", "评审", "沟通", "协作",
}

# 技能词正则
_SKILL_EN = re.compile(r"[A-Z][A-Za-z+#./0-9]{1,25}")
_SKILL_CN = re.compile(r"[一-鿿]{2,8}")


def _normalize_skill(s: str) -> str:
    """归一化技能名"""
    s = s.strip()
    if not s:
        return s
    lower = s.lower()
    if lower in ALIASES:
        return ALIASES[lower]
    if s.isascii() and s.isalpha():
        return s[0].upper() + s[1:].lower()
    return s


def _extract_skills_from_text(text_value: str) -> list[dict]:
    """从全文提取技能词，归一化 + 去重"""
    from tools.skill_taxonomy import KNOWN_SKILLS
    skills = []
    seen = set()

    # 段落标题识别能力要求段
    req_pattern = re.compile(r"(任职要求|岗位要求|必备条件|能力要求|Requirements)", re.I)
    nice_pattern = re.compile(r"(加分项|优先|熟悉更佳|nice.to.have|bonus)", re.I)

    sections = req_pattern.split(text_value)
    for i, section in enumerate(sections):
        if req_pattern.match(section):
            if i + 1 < len(sections):
                content = sections[i + 1]
                if nice_pattern.search(content):
                    content = nice_pattern.split(content)[0]
                for match in _SKILL_EN.finditer(content):
                    s = _normalize_skill(match.group())
                    if s.lower() not in seen and s.lower() not in {w.lower() for w in _SKILL_STOP}:
                        seen.add(s.lower())
                        skills.append({"skill": s, "confidence": "explicit"})
                for match in _SKILL_CN.finditer(content):
                    s = match.group().strip()
                    if s.lower() not in seen and s not in _SKILL_STOP and len(s) >= 2:
                        seen.add(s.lower())
                        skills.append({"skill": s, "confidence": "explicit"})

    # 兜底：扫描"熟悉/掌握/精通"句式
    if not skills:
        for s in _split_sentences(text_value):
            if any(k in s for k in ("熟悉", "掌握", "精通", "具备", "了解", "擅长")):
                for match in _SKILL_EN.finditer(s):
                    sk = _normalize_skill(match.group())
                    if sk.lower() not in seen and sk.lower() not in {w.lower() for w in _SKILL_STOP}:
                        seen.add(sk.lower())
                        skills.append({"skill": sk, "confidence": "inferred"})
                for match in _SKILL_CN.finditer(s):
                    sk = match.group().strip()
                    if sk.lower() not in seen and sk not in _SKILL_STOP and len(sk) >= 2:
                        seen.add(sk.lower())
                        skills.append({"skill": sk, "confidence": "inferred"})

    # 补漏：全文匹配 KNOWN_SKILLS
    text_lower = text_value.lower()
    for known in KNOWN_SKILLS:
        if known.lower() in text_lower and known.lower() not in seen:
            seen.add(known.lower())
            skills.append({"skill": known, "confidence": "inferred"})

    # 补漏：匹配冒号/顿号分隔的技能列表（"技能：SQL、Python、Pandas"）
    skill_list_pattern = re.compile(r"(?:技能|skills|掌握|熟悉)[：:]\s*(.+?)(?:\n|$)", re.I)
    for match in skill_list_pattern.finditer(text_value):
        items = re.split(r"[、,，\s]+", match.group(1))
        for item in items:
            s = _normalize_skill(item.strip())
            if s and len(s) >= 2 and s.lower() not in seen and s.lower() not in {w.lower() for w in _SKILL_STOP}:
                seen.add(s.lower())
                skills.append({"skill": s, "confidence": "explicit"})

    return skills[:20]


def _extract_projects(text_value: str) -> list[dict]:
    """从简历中提取项目经历"""
    projects = []
    seen = set()

    # 项目段落标题
    proj_pattern = re.compile(r"(项目经历|项目经验|个人项目|课程项目|实战项目|开源项目)", re.I)
    sections = proj_pattern.split(text_value)
    for i, section in enumerate(sections):
        if proj_pattern.match(section):
            if i + 1 < len(sections):
                content = sections[i + 1][:500]
                for s in _split_sentences(content):
                    s = s.strip()
                    if len(s) < 6:
                        continue
                    # 停止条件：遇到工作/实习/教育
                    if any(k in s for k in ("工作经历", "实习经历", "教育背景", "学历")):
                        break
                    if s not in seen:
                        seen.add(s)
                        projects.append(s[:200])

    # 兜底：扫描"项目"关键词
    if not projects:
        for s in _split_sentences(text_value):
            if any(k in s for k in ("项目", "平台", "系统", "工具", "网站")) and len(s) > 10:
                if s not in seen:
                    seen.add(s)
                    projects.append(s[:200])

    return [{"name": p[:30], "description": p, "confidence": "explicit"} for p in projects[:6]]


def _extract_internships(text_value: str) -> list[dict]:
    """提取实习经历"""
    internships = []
    seen = set()

    # 实习段落标题
    intern_pattern = re.compile(r"(实习经历|实习经验|实习)", re.I)
    sections = intern_pattern.split(text_value)
    for i, section in enumerate(sections):
        if intern_pattern.match(section):
            if i + 1 < len(sections):
                content = sections[i + 1][:400]
                for s in _split_sentences(content):
                    s = s.strip()
                    if len(s) < 6:
                        continue
                    if any(k in s for k in ("工作经历", "教育背景", "项目经历")):
                        break
                    if s not in seen:
                        seen.add(s)
                        internships.append({"description": s[:180], "confidence": "explicit"})

    # 兜底：扫描"实习"关键词
    if not internships:
        for s in _split_sentences(text_value):
            if "实习" in s and len(s) > 6:
                if s not in seen:
                    seen.add(s)
                    internships.append({"description": s[:180], "confidence": "inferred"})

    return internships[:6]


def _extract_work_experiences(text_value: str) -> list[dict]:
    """提取工作经历"""
    experiences = []
    seen = set()

    # 工作段落标题
    work_pattern = re.compile(r"(工作经历|工作经验|任职经历)", re.I)
    sections = work_pattern.split(text_value)
    for i, section in enumerate(sections):
        if work_pattern.match(section):
            if i + 1 < len(sections):
                content = sections[i + 1][:500]
                for s in _split_sentences(content):
                    s = s.strip()
                    if len(s) < 6:
                        continue
                    if any(k in s for k in ("教育背景", "项目经历", "实习")):
                        break
                    if s not in seen:
                        seen.add(s)
                        experiences.append({"description": s[:180], "confidence": "explicit"})

    # 兜底：扫描"任职/工作于/就职/工作："关键词（排除项目和实习）
    if not experiences:
        for s in _split_sentences(text_value):
            if any(k in s for k in ("任职", "工作于", "就职", "工作：", "工作:")) and len(s) > 6:
                if "实习" not in s and "项目" not in s:
                    if s not in seen:
                        seen.add(s)
                        experiences.append({"description": s[:180], "confidence": "inferred"})

    return experiences[:8]


def _extract_achievements(text_value: str) -> list[dict]:
    """提取成果证据"""
    achievements = []
    seen = set()
    for s in _split_sentences(text_value):
        if re.search(r"\d+[%万千]|提升|降低|优化|上线|获奖|竞赛|专利|论文|部署|落地|交付|准确率|召回率|延迟|QPS|TopK", s):
            s_clean = s.strip()[:150]
            if s_clean and s_clean not in seen:
                seen.add(s_clean)
                achievements.append({
                    "description": s_clean,
                    "has_metric": bool(re.search(r"\d+[%万千]", s)),
                })
    return achievements[:8]


def _extract_learning_signals(text_value: str) -> list[str]:
    """提取学习能力信号"""
    signals = []
    patterns = [
        (r"(自学|自研|独立学习|独立完成|从0到1|从零开始)", "自主学习"),
        (r"(开源|github|GitHub|贡献)", "开源参与"),
        (r"(竞赛|比赛|hackathon|Hackathon)", "竞赛经历"),
        (r"(论文|专利|博客|技术文章)", "技术输出"),
        (r"(证书|认证|考取)", "认证获取"),
        (r"(新技术|新框架|快速上手|快速学习)", "技术迁移"),
        (r"(跨专业|跨领域|转行)", "跨领域学习"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, text_value, re.I):
            signals.append(label)
    return signals


def _extract_business_understanding(text_value: str) -> list[str]:
    """提取业务理解信号"""
    domains = []
    domain_keywords = {
        "电商": ("电商", "商城", "购物", "下单", "订单"),
        "金融": ("金融", "支付", "风控", "交易", "银行"),
        "教育": ("教育", "在线学习", "课程", "教学"),
        "医疗": ("医疗", "健康", "医院", "问诊"),
        "游戏": ("游戏", "引擎", "Unity", "游戏开发"),
        "社交": ("社交", "IM", "消息", "即时通讯"),
        "企业服务": ("SaaS", "CRM", "ERP", "OA", "企业服务"),
        "AI": ("AI", "人工智能", "大模型", "LLM", "Agent"),
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
        (r"(沟通|表达|汇报|演示)", "沟通表达"),
        (r"(带领|负责|leader|lead)", "领导力"),
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
    achievements = _extract_achievements(text_value)
    learning = _extract_learning_signals(text_value)
    business = _extract_business_understanding(text_value)
    collab = _extract_collaboration_signals(text_value)
    sensitive = _detect_sensitive_info(text_value)

    # 技能栈：优先 LLM，失败走规则兜底
    from services.resume_profile import extract_profile_from_text, profile_to_skill_names
    base = extract_profile_from_text(text_value, use_llm=True) if text_value else {"skills": [], "summary": "", "parser": "empty"}
    skill_stack = []
    for item in base.get("skills", []):
        name = item if isinstance(item, str) else item.get("skill", "")
        conf = "explicit" if isinstance(item, dict) and item.get("confidence", 0) >= 0.7 else "inferred"
        skill_stack.append({"skill": str(name), "confidence": conf})

    # 如果 LLM 没提取到技能，走规则兜底
    if not skill_stack and text_value:
        logger.info("LLM 未提取到技能，使用规则兜底")
        skill_stack = _extract_skills_from_text(text_value)

    # 项目/实习/工作经历：规则提取（不依赖 LLM）
    projects = _extract_projects(text_value)
    internships = _extract_internships(text_value)
    work_experiences = _extract_work_experiences(text_value)

    # 经历年限
    exp_years = _estimate_experience_years(text_value)

    # 风险点
    risks = []
    if not education.get("degree"):
        risks.append("未明确学历")
    if not projects and not internships:
        risks.append("缺少项目/实习经历")
    if not achievements:
        risks.append("缺少量化成果")

    # 置信度
    has_degree = bool(education.get("degree"))
    conf = "high" if (skill_stack and projects and has_degree) else "medium" if skill_stack else "low"

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
        internships=internships,
        work_experiences=work_experiences,
        business_understanding=business,
        achievements=achievements,
        learning_signals=learning,
        transferable_strengths=collab,
        collaboration_signals=collab,
        risk_points=risks,
        evidence=evidence,
        confidence=conf,
        sensitive_detected=sensitive,
        summary=f"识别到 {len(skill_stack)} 个技能、{len(projects)} 个项目经历、{len(internships)} 段实习。",
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
