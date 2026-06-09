"""Job profile extraction service — v0.9"""
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
from services.profile_schemas import JobProfileResult, EvidenceItem
from tools.skill_guard import normalize_job_name
from tools.skill_taxonomy import filter_skill_names
from core.logger import get_logger

logger = get_logger(__name__)


def extract_job_profile(job_name: str, top_n: int = 20) -> JobProfileResult:
    """从 JD 样本中提取结构化岗位画像"""
    job_name = normalize_job_name(job_name)
    jd_items = _fetch_jd_texts(job_name, limit=20)
    jd_items = _filter_jd_quality(jd_items)
    texts = [item["text"] for item in jd_items if item.get("text")]
    stage = _infer_job_stage(job_name, texts)
    emp = _infer_employment_type(texts)

    # 核心职责
    responsibilities = []
    for t in texts:
        for s in re.split(r"[。；\n]", t):
            if any(k in s for k in ("负责", "参与", "承担", "主导", "完成")) and len(s.strip()) > 8:
                responsibilities.append(s.strip()[:120])
    responsibilities = list(dict.fromkeys(responsibilities))[:8]

    # 能力要求
    edu_req = _extract_education_requirements(texts)
    major_req = _extract_major_requirements(texts)
    exp_req = _extract_experience_requirements(texts)
    soft = _count_hits(texts, SOFT_REQUIREMENTS)
    domains = _count_hits(texts, BUSINESS_DOMAINS)

    # 从 JD 文本提取技能词
    all_sentences = []
    for t in texts:
        all_sentences.extend(re.split(r"[。；\n]", t))
    skill_sentences = [s for s in all_sentences if any(k in s for k in ("熟悉", "掌握", "了解", "精通", "具备", "会", "使用"))]
    must_have = filter_skill_names([s.strip()[:30] for s in skill_sentences[:20]], job_name=job_name)[:10]

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
    conf = "high" if len(jd_items) >= 8 else "medium" if len(jd_items) >= 3 else "low"

    # 质量标记
    flags = []
    if len(jd_items) < 3:
        flags.append("样本不足")
    if not must_have:
        flags.append("未提取到明确技能要求")

    return JobProfileResult(
        job_name=job_name,
        job_type=stage["job_type"],
        employment_type=emp["employment_type"],
        target_audience=stage["target_audience"],
        responsibilities=responsibilities,
        must_have_capabilities=must_have,
        nice_to_have_capabilities=[s["name"] for s in soft[:5]],
        experience_requirement=exp_req[0]["value"] if exp_req else "未明确",
        education_preference=edu_req[0]["degree"] if edu_req else "未明确",
        major_preference="、".join(m["major"] for m in major_req[:3]) if major_req else "未明确",
        business_context=[d["name"] for d in domains[:5]],
        growth_context=growth,
        evidence=evidence,
        confidence=conf,
        quality_flags=flags,
        sample_count=len(jd_items),
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
