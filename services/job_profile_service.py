"""Job profile extraction service — v0.16 增强提取逻辑"""
from __future__ import annotations
import json
import re
from datetime import datetime
from services.screening import (
    _fetch_jd_texts, _filter_jd_quality, _infer_job_stage,
    _infer_employment_type, _extract_education_requirements,
    _extract_major_requirements, _extract_experience_requirements,
    _count_hits, BUSINESS_DOMAINS, SOFT_REQUIREMENTS, DEGREES, MAJOR_HINTS,
)
from services.jd_quality_service import filter_jd_items
from services.profile_schemas import JobProfileResult, EvidenceItem
from tools.skill_guard import normalize_job_name, ALIASES
from tools.skill_taxonomy import filter_skill_names, KNOWN_SKILLS
from core.logger import get_logger

logger = get_logger(__name__)

# 职责段落标题关键词
_RESPONSIBILITY_HEADERS = re.compile(
    r"(岗位职责|工作职责|你将负责|工作内容|职责描述|Responsibilities|What you.ll do)",
    re.I,
)

# 要求段落标题关键词
_REQUIREMENT_HEADERS = re.compile(
    r"(任职要求|岗位要求|必备条件|任职资格|我们希望你|Requirements|What we need)",
    re.I,
)

# 加分/优先段落标题
_NICE_TO_HAVE_HEADERS = re.compile(
    r"(加分项|优先|熟悉更佳|nice.to.have|bonus|加分条件)",
    re.I,
)

# 技能关键词提取正则：从"熟悉Python、掌握Django"中提取具体技能名
_SKILL_EXTRACT_PATTERNS = [
    # 英文技能名（Python, FastAPI, MySQL, React.js 等）
    re.compile(r"[A-Z][A-Za-z+#./0-9]{1,25}"),
    # 中文技能名（大模型、微服务、分布式等）
    re.compile(r"[一-鿿]{2,8}"),
]

# 停用词——不是技能
_SKILL_STOP_WORDS = {
    "熟悉", "掌握", "了解", "精通", "具备", "使用", "具有", "会",
    "以上", "优先", "经验", "能力", "技术", "开发", "工程师",
    "相关", "学历", "专业", "本科", "硕士", "博士", "大专",
    "年以上", "应届", "实习", "工作", "岗位", "职责", "要求",
    "沟通", "协作", "团队", "学习", "能力", "抗压", "责任心",
    "逻辑思维", "表达", "推动", "执行", "跨部门",
    "五险一金", "年终奖", "带薪年假", "节日福利", "团建",
}


def _extract_skills_from_section(text: str) -> list[str]:
    """从文本中提取技能词，返回去重归一化列表"""
    skills = []
    seen = set()
    for sentence in re.split(r"[。；\n,，]", text):
        sentence = sentence.strip()
        if len(sentence) < 2:
            continue
        for pattern in _SKILL_EXTRACT_PATTERNS:
            for match in pattern.finditer(sentence):
                skill = match.group().strip()
                if len(skill) < 2 or skill.lower() in _SKILL_STOP_WORDS:
                    continue
                normalized = _normalize_skill(skill)
                if normalized.lower() not in seen:
                    seen.add(normalized.lower())
                    skills.append(normalized)
    return skills


def _normalize_skill(skill: str) -> str:
    """归一化技能名：别名映射 + 大小写统一"""
    s = skill.strip()
    if not s:
        return s
    lower = s.lower()
    if lower in ALIASES:
        return ALIASES[lower]
    # 首字母大写处理
    if s.isascii() and s.isalpha():
        return s[0].upper() + s[1:].lower()
    return s


def _extract_responsibilities(texts: list[str]) -> list[str]:
    """从 JD 中提取岗位职责"""
    responsibilities = []
    seen = set()

    for text in texts:
        # 找职责段落
        sections = _RESPONSIBILITY_HEADERS.split(text)
        for i, section in enumerate(sections):
            if _RESPONSIBILITY_HEADERS.match(section):
                # 下一段就是职责内容
                if i + 1 < len(sections):
                    content = sections[i + 1]
                    for s in re.split(r"[。；\n]", content):
                        s = s.strip()
                        # 停止条件：遇到要求/任职/薪资等段落
                        if _REQUIREMENT_HEADERS.match(s) or len(s) < 6:
                            continue
                        if any(k in s for k in ("负责", "参与", "承担", "主导", "完成", "推动", "设计", "开发", "维护", "优化")):
                            if s not in seen:
                                seen.add(s)
                                responsibilities.append(s[:120])

        # 兜底：没找到标题时，扫描关键词
        if not responsibilities:
            for s in re.split(r"[。；\n]", text):
                s = s.strip()
                if any(k in s for k in ("负责", "参与", "承担", "主导")) and len(s) > 8:
                    if s not in seen:
                        seen.add(s)
                        responsibilities.append(s[:120])

    return responsibilities[:8]


def _extract_must_have_skills(texts: list[str]) -> list[str]:
    """从 JD 中提取必备技能"""
    all_skills = []
    seen = set()

    for text in texts:
        # 找要求段落
        sections = _REQUIREMENT_HEADERS.split(text)
        for i, section in enumerate(sections):
            if _REQUIREMENT_HEADERS.match(section):
                if i + 1 < len(sections):
                    content = sections[i + 1]
                    # 排除加分/优先段落
                    if _NICE_TO_HAVE_HEADERS.search(content):
                        content = _NICE_TO_HAVE_HEADERS.split(content)[0]
                    skills = _extract_skills_from_section(content)
                    for s in skills:
                        if s.lower() not in seen:
                            seen.add(s.lower())
                            all_skills.append(s)

        # 兜底：扫描"熟悉/掌握/精通"关键词所在的句子
        if not all_skills:
            for s in re.split(r"[。；\n]", text):
                if any(k in s for k in ("熟悉", "掌握", "精通", "具备", "了解", "擅长")):
                    skills = _extract_skills_from_section(s)
                    for sk in skills:
                        if sk.lower() not in seen:
                            seen.add(sk.lower())
                            all_skills.append(sk)

    # 始终从全文匹配 CAPABILITY_WHITELIST 中的已知能力词（补漏）
    from tools.skill_guard import CAPABILITY_WHITELIST
    for text in texts:
        text_lower = text.lower()
        for cap in CAPABILITY_WHITELIST:
            if cap.lower() in text_lower and cap.lower() not in seen:
                seen.add(cap.lower())
                all_skills.append(cap)

    # 过滤：保留技术/能力词，去掉过泛词
    return filter_skill_names(all_skills, job_name="")[:15]


def _extract_nice_to_have_skills(texts: list[str]) -> list[str]:
    """从 JD 中提取加分/优先技能"""
    all_skills = []
    seen = set()

    for text in texts:
        # 找加分段落
        sections = _NICE_TO_HAVE_HEADERS.split(text)
        for i, section in enumerate(sections):
            if _NICE_TO_HAVE_HEADERS.match(section):
                if i + 1 < len(sections):
                    content = sections[i + 1][:200]  # 只取前 200 字
                    skills = _extract_skills_from_section(content)
                    for s in skills:
                        if s.lower() not in seen:
                            seen.add(s.lower())
                            all_skills.append(s)

    return filter_skill_names(all_skills, job_name="")[:8]


def extract_job_profile(job_name: str, top_n: int = 20, raw_jd_texts: list[str] = None) -> JobProfileResult:
    """从 JD 样本中提取结构化岗位画像。
    raw_jd_texts 非空时优先使用（如 Golden Set 评测），否则从数据库读取。
    """
    job_name = normalize_job_name(job_name)

    if raw_jd_texts:
        jd_items = [{"text": t, "title": "", "company": "", "source_url": "", "fetched_at": ""} for t in raw_jd_texts]
    else:
        jd_items = _fetch_jd_texts(job_name, limit=20)

    raw_count = len(jd_items)

    # JD 质量过滤 + 去重
    valid_jds, filtered_jds, quality_summary = filter_jd_items(jd_items, job_name=job_name)
    jd_items = valid_jds
    texts = [item["text"] for item in jd_items if item.get("text")]
    stage = _infer_job_stage(job_name, texts)
    emp = _infer_employment_type(texts)

    # 核心职责
    responsibilities = _extract_responsibilities(texts)

    # 能力要求
    edu_req = _extract_education_requirements(texts)
    major_req = _extract_major_requirements(texts)
    exp_req = _extract_experience_requirements(texts)
    soft = _count_hits(texts, SOFT_REQUIREMENTS)
    domains = _count_hits(texts, BUSINESS_DOMAINS)

    # 必备技能和加分技能分别提取
    must_have = _extract_must_have_skills(texts)
    nice_to_have = _extract_nice_to_have_skills(texts)

    # 去重：nice_to_have 中去掉已在 must_have 中的
    must_set = {s.lower() for s in must_have}
    nice_to_have = [s for s in nice_to_have if s.lower() not in must_set]

    # 成长空间
    growth = []
    for t in texts:
        for s in re.split(r"[。；\n]", t):
            if any(k in s for k in ("发展", "晋升", "成长", "培训", "学习", "进阶")) and len(s.strip()) > 5:
                growth.append(s.strip()[:100])
    growth = list(dict.fromkeys(growth))[:5]

    # 证据片段
    evidence = []
    for item in jd_items[:3]:
        evidence.append(EvidenceItem(
            text=item["text"][:200],
            source=f"{item.get('company', '')} - {item.get('title', '')}",
        ))

    # 置信度
    valid_count = len(jd_items)
    conf = "high" if valid_count >= 8 else "medium" if valid_count >= 3 else "low"

    # 质量标记
    flags = []
    if valid_count < 3:
        flags.append("有效样本不足")
    if raw_count > 0 and valid_count < raw_count * 0.3:
        flags.append("有效样本比例过低")
    if not must_have:
        flags.append("未提取到明确技能要求")
    if quality_summary.get("avg_quality_score", 0) < 50:
        flags.append("JD 整体质量偏低")

    return JobProfileResult(
        job_name=job_name,
        job_type=stage["job_type"],
        employment_type=emp["employment_type"],
        target_audience=stage["target_audience"],
        responsibilities=responsibilities,
        must_have_capabilities=must_have,
        nice_to_have_capabilities=nice_to_have,
        experience_requirement=exp_req[0]["value"] if exp_req else "未明确",
        education_preference=edu_req[0]["degree"] if edu_req else "未明确",
        major_preference="、".join(m["major"] for m in major_req[:3]) if major_req else "未明确",
        business_context=[d["name"] for d in domains[:5]],
        growth_context=growth,
        evidence=evidence,
        confidence=conf,
        quality_flags=flags,
        sample_count=valid_count,
        valid_sample_count=valid_count,
        filtered_sample_count=raw_count - valid_count,
    )


def save_job_profile(profile: JobProfileResult, source_doc_ids: list[int] = None) -> int:
    """保存岗位画像到数据库，返回 ID"""
    from models.database import SessionLocal
    from models.profile import JobProfile
    with SessionLocal() as session:
        obj = JobProfile(
            job_name=profile.job_name,
            profile_version="1.0",
            source_document_ids=json.dumps(source_doc_ids or []),
            sample_count=profile.sample_count,
            job_type=profile.job_type,
            employment_type=profile.employment_type,
            target_audience=profile.target_audience,
            responsibilities=json.dumps(profile.responsibilities, ensure_ascii=False),
            must_have_capabilities=json.dumps(profile.must_have_capabilities, ensure_ascii=False),
            nice_to_have_capabilities=json.dumps(profile.nice_to_have_capabilities, ensure_ascii=False),
            experience_requirement=profile.experience_requirement,
            education_preference=profile.education_preference,
            major_preference=profile.major_preference,
            business_context=json.dumps(profile.business_context, ensure_ascii=False),
            growth_context=json.dumps(profile.growth_context, ensure_ascii=False),
            evidence=json.dumps([e.model_dump() for e in profile.evidence], ensure_ascii=False),
            confidence=profile.confidence,
            quality_flags=json.dumps(profile.quality_flags, ensure_ascii=False),
        )
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.id
