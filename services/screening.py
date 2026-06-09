"""Job/candidate profile extraction and resume screening simulation — v0.8."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from services.resume_profile import extract_profile_from_text, profile_to_skill_names
from tools.skill_guard import ALIASES, normalize_job_name
from tools.skill_taxonomy import enrich_skill_item


DEGREES = ("博士", "硕士", "研究生", "本科", "大专", "专科")
DEGREE_RANK = {"": 0, "大专": 1, "专科": 1, "本科": 2, "硕士": 3, "研究生": 3, "博士": 4}
MAJOR_HINTS = (
    "计算机", "软件工程", "数据科学", "统计", "数学", "人工智能", "电子",
    "通信", "自动化", "信息管理", "工商管理", "市场营销", "设计",
)
BUSINESS_DOMAINS = (
    "电商", "金融", "教育", "医疗", "游戏", "广告", "零售", "物流",
    "制造", "IoT", "物联网", "SaaS", "云计算", "安全", "招聘", "人力资源",
)
SOFT_REQUIREMENTS = (
    "沟通", "协作", "学习能力", "抗压", "责任心", "执行力", "逻辑思维",
    "推动", "表达", "团队合作", "跨部门",
)
EXPERIENCE_PATTERNS = (
    r"(\d+)\s*[-~到至]\s*(\d+)\s*年",
    r"(\d+)\s*年(?:以上|及以上|\+)?",
    r"不少于\s*(\d+)\s*年",
)
EMPLOYMENT_TYPE_KEYWORDS = {
    "全职": ("全职", "正式", "长期"),
    "兼职": ("兼职", "part-time"),
    "实习": ("实习", "intern", "internship"),
    "合同": ("合同", "外包", "派遣"),
}

# 敏感信息模式——评分时禁止使用
SENSITIVE_PATTERNS = re.compile(
    r"(年龄|性别|男|女|婚否|已婚|未婚|民族|政治面貌|党员|户籍|籍贯|身高|体重|外貌)",
    re.I,
)


def query_skill_rank(job_name: str, top_n: int = 20) -> list[dict]:
    """Lazy wrapper so this module remains importable without DB dependencies."""
    from memory.long_term import query_skill_rank as _query_skill_rank
    return _query_skill_rank(job_name, top_n=top_n)


def _normalize_skill(skill) -> str:
    if not isinstance(skill, str):
        return ""
    s = skill.strip()
    if not s:
        return ""
    return ALIASES.get(s.lower(), s)


def filter_market_skills(raw_market: list[dict], job_name: str = "", top_n: int = 20) -> list[dict]:
    market = []
    for item in raw_market:
        enriched = enrich_skill_item(item, job_name=job_name)
        if enriched:
            market.append(enriched)
    return market[:top_n]


def _split_sentences(text_value: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？；;\n]", text_value or "") if s.strip()]


def _filter_jd_quality(jd_items: list[dict]) -> list[dict]:
    """过滤低质量 JD：过短、泛化、重复、无岗位信息"""
    seen_hashes = set()
    filtered = []
    for item in jd_items:
        text = (item.get("text") or "").strip()
        # 过短
        if len(text) < 80:
            continue
        # 去重（前200字 hash）
        h = hash(text[:200])
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        # 无岗位关键词
        lower = text.lower()
        has_job_keyword = any(k in lower for k in ("岗位", "职责", "要求", "任职", "招聘", "职位", "工作内容", "job", "requirement"))
        if not has_job_keyword and len(text) < 200:
            continue
        filtered.append(item)
    return filtered


def _fetch_jd_texts(job_name: str, limit: int = 20) -> list[dict]:
    from sqlalchemy import text
    from models.database import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(
            text(
                "SELECT title, company, raw_text, source_url, fetched_at "
                "FROM jd_documents WHERE job_name = :job "
                "ORDER BY fetched_at DESC LIMIT :limit"
            ),
            {"job": normalize_job_name(job_name), "limit": limit},
        ).fetchall()
    return [
        {
            "title": r[0] or "",
            "company": r[1] or "",
            "text": r[2] or "",
            "source_url": r[3] or "",
            "fetched_at": r[4].isoformat() if hasattr(r[4], "isoformat") else (r[4] or ""),
        }
        for r in rows
    ]


def _count_hits(texts: list[str], terms: tuple[str, ...]) -> list[dict]:
    counter = Counter()
    evidence = {}
    for sentence in _split_sentences("\n".join(texts)):
        lower = sentence.lower()
        for term in terms:
            if term.lower() in lower:
                counter[term] += 1
                evidence.setdefault(term, sentence[:160])
    return [
        {"name": term, "count": cnt, "evidence": evidence.get(term, "")}
        for term, cnt in counter.most_common()
    ]


def _infer_job_stage(job_name: str, texts: list[str]) -> dict:
    joined = f"{job_name}\n" + "\n".join(texts[:10])
    if re.search(r"(实习|intern|internship)", joined, re.I):
        return {"job_type": "实习", "target_audience": "在校生/应届生", "confidence": "high"}
    if re.search(r"(校招|应届|毕业生|管培)", joined):
        return {"job_type": "校招", "target_audience": "应届生", "confidence": "high"}
    if re.search(r"(社招|经验|[1-9]\s*年)", joined):
        return {"job_type": "正式", "target_audience": "有经验候选人", "confidence": "medium"}
    return {"job_type": "未知", "target_audience": "未明确", "confidence": "low"}


def _extract_experience_requirements(texts: list[str]) -> list[dict]:
    requirements = []
    seen = set()
    for sentence in _split_sentences("\n".join(texts)):
        if "经验" not in sentence and "年" not in sentence and "实习" not in sentence:
            continue
        for pattern in EXPERIENCE_PATTERNS:
            match = re.search(pattern, sentence)
            if not match:
                continue
            value = match.group(0)
            if value in seen:
                continue
            seen.add(value)
            requirements.append({"value": value, "evidence": sentence[:180]})
            break
        if "实习" in sentence and "实习经历" not in seen:
            seen.add("实习经历")
            requirements.append({"value": "实习经历", "evidence": sentence[:180]})
    return requirements[:8]


def _extract_education_requirements(texts: list[str]) -> list[dict]:
    requirements = []
    seen = set()
    for sentence in _split_sentences("\n".join(texts)):
        if not any(degree in sentence for degree in DEGREES):
            continue
        for degree in DEGREES:
            if degree in sentence and degree not in seen:
                seen.add(degree)
                requirements.append({"degree": degree, "evidence": sentence[:180]})
    return requirements[:6]


def _extract_major_requirements(texts: list[str]) -> list[dict]:
    results = []
    seen = set()
    for sentence in _split_sentences("\n".join(texts)):
        if "专业" not in sentence and not any(m in sentence for m in MAJOR_HINTS):
            continue
        for major in MAJOR_HINTS:
            if major in sentence and major not in seen:
                seen.add(major)
                results.append({"major": major, "evidence": sentence[:180]})
    return results[:8]


def _infer_employment_type(texts: list[str]) -> dict:
    """从 JD 文本推断用工类型"""
    joined = "\n".join(texts).lower()
    for etype, keywords in EMPLOYMENT_TYPE_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw.lower() in joined)
        if hits >= 1:
            return {"employment_type": etype, "confidence": "high" if hits >= 2 else "medium"}
    return {"employment_type": "未知", "confidence": "low"}


def _extract_experience_years_required(texts: list[str]) -> list[dict]:
    """提取经验年限要求，每条带 evidence"""
    return _extract_experience_requirements(texts)  # 复用现有逻辑


def build_job_profile(job_name: str, top_n: int = 20) -> dict:
    """Build a multi-dimensional job profile from stored JD samples and skill rank."""
    job_name = normalize_job_name(job_name)
    top_n = max(1, min(top_n, 50))
    raw_market = query_skill_rank(job_name, top_n=min(top_n * 2, 50))
    market_skills = filter_market_skills(raw_market, job_name=job_name, top_n=top_n)
    jd_items = _fetch_jd_texts(job_name, limit=20)
    jd_items = _filter_jd_quality(jd_items)
    texts = [item["text"] for item in jd_items if item.get("text")]
    stage = _infer_job_stage(job_name, texts)
    emp = _infer_employment_type(texts)
    total_jds = market_skills[0].get("total_jds", 0) if market_skills else len(jd_items)

    hard_skills = []
    for idx, item in enumerate(market_skills):
        count = item.get("count", 0) or 0
        ratio = count / total_jds if total_jds else 0
        importance = "must" if idx < 5 or ratio >= 0.45 else "nice"
        hard_skills.append({
            "name": item["skill"],
            "count": count,
            "total_jds": item.get("total_jds", total_jds),
            "frequency": round(ratio, 3) if total_jds else 0,
            "importance": importance,
            "confidence": item.get("confidence", "medium"),
        })

    edu_req = _extract_education_requirements(texts)
    major_req = _extract_major_requirements(texts)
    exp_req = _extract_experience_requirements(texts)

    last_update = ""
    for item in jd_items:
        if item.get("fetched_at"):
            last_update = item["fetched_at"][:19].replace("T", " ")
            break

    return {
        "job_name": job_name,
        "job_type": stage["job_type"],
        "employment_type": emp["employment_type"],
        "target_audience": stage["target_audience"],
        "stage_confidence": stage["confidence"],
        "education_requirements": edu_req,
        "major_requirements": major_req,
        "experience_requirements": exp_req,
        "hard_skills": hard_skills,
        "must_have": [s["name"] for s in hard_skills if s["importance"] == "must"],
        "nice_to_have": [s["name"] for s in hard_skills if s["importance"] == "nice"][:10],
        "business_domains": _count_hits(texts, BUSINESS_DOMAINS)[:8],
        "soft_requirements": _count_hits(texts, SOFT_REQUIREMENTS)[:8],
        "sample": {
            "jd_count": len(jd_items),
            "raw_jd_count": len(_fetch_jd_texts(job_name, limit=20)),
            "skill_sample_jds": total_jds,
            "last_update": last_update,
            "titles": [item["title"] for item in jd_items[:5] if item.get("title")],
        },
        "summary": (
            f"「{job_name}」画像：{stage['job_type']}/{emp['employment_type']}岗位，面向{stage['target_audience']}；"
            f"识别到 {len(hard_skills)} 个市场技能、{len(jd_items)} 条JD样本。"
        ),
    }


def _extract_candidate_education(text_value: str) -> dict:
    degree = ""
    for d in DEGREES:
        if d in text_value:
            degree = d
            break
    major = ""
    for m in MAJOR_HINTS:
        if m in text_value:
            major = m
            break
    years = re.findall(r"(20\d{2})\s*(?:年)?\s*(?:毕业|届|入学)?", text_value)
    schools = []
    for sentence in _split_sentences(text_value):
        if any(k in sentence for k in ("大学", "学院", "学校")):
            schools.append(sentence[:120])
    return {
        "degree": degree,
        "major": major,
        "graduation_year": years[-1] if years else "",
        "school_evidence": schools[:3],
    }


def _estimate_experience_years(text_value: str) -> dict:
    """估算候选人工作年限，区分 explicit 和 inferred"""
    # 明确年限声明
    explicit = re.findall(r"(\d+)\s*年(?:工作经验|经验|以上)", text_value)
    if explicit:
        return {"years": int(explicit[0]), "confidence": "explicit", "source": "简历明确声明"}

    # 从毕业年份推断
    grad_years = re.findall(r"(20\d{2})\s*(?:年)?\s*(?:毕业|届)", text_value)
    if grad_years:
        current_year = datetime.now().year
        yrs = current_year - int(grad_years[0])
        if yrs >= 0:
            return {"years": max(0, yrs), "confidence": "inferred", "source": f"毕业年份{grad_years[0]}推算"}

    # 从实习/工作经历段落推断
    sentences = _split_sentences(text_value)
    work_sentences = [s for s in sentences if any(k in s for k in ("工作", "任职", "负责", "公司"))]
    if work_sentences:
        return {"years": max(1, len(work_sentences) // 2), "confidence": "inferred", "source": "工作经历段落数推算"}

    return {"years": 0, "confidence": "unknown", "source": "未找到年限线索"}


def _extract_candidate_experience(text_value: str) -> dict:
    sentences = _split_sentences(text_value)
    internships = [s[:180] for s in sentences if "实习" in s][:6]
    work = [s[:180] for s in sentences if any(k in s for k in ("工作", "任职", "负责", "公司"))][:8]
    projects = [s[:180] for s in sentences if any(k in s for k in ("项目", "平台", "系统", "产品"))][:10]
    metrics = [s[:180] for s in sentences if re.search(r"\d+[%万千]?|提升|降低|优化|上线", s)][:8]
    exp_years = _estimate_experience_years(text_value)
    return {
        "internships": internships,
        "work_experience": work,
        "projects": projects,
        "metrics": metrics,
        "has_internship": bool(internships),
        "has_project": bool(projects),
        "experience_years": exp_years["years"],
        "experience_years_confidence": exp_years["confidence"],
        "experience_years_source": exp_years["source"],
    }


def _detect_sensitive_info(text_value: str) -> list[str]:
    """检测简历中的敏感信息（不参与评分，仅报告）"""
    found = []
    for match in SENSITIVE_PATTERNS.finditer(text_value or ""):
        term = match.group().strip()
        if term and term not in found:
            found.append(term)
    return found[:5]


def extract_candidate_profile(resume_text: str = "", user_profile: list[dict] | dict | None = None) -> dict:
    """Build a candidate profile from resume text and/or existing skill profile."""
    resume_text = (resume_text or "").strip()
    base = extract_profile_from_text(resume_text, use_llm=True) if resume_text else {"skills": [], "summary": "", "parser": "empty"}
    if user_profile:
        merged = []
        seen = set()
        for item in [*base.get("skills", []), *list(user_profile.get("skills", []) if isinstance(user_profile, dict) else user_profile)]:
            name = item if isinstance(item, str) else item.get("skill", "")
            key = str(name).strip().lower()
            if key and key not in seen:
                seen.add(key)
                merged.append(item if isinstance(item, dict) else {"skill": str(item), "source": "manual", "confidence": 0.65})
        base["skills"] = merged
    education = _extract_candidate_education(resume_text)
    experience = _extract_candidate_experience(resume_text)
    return {
        "skills": base.get("skills", []),
        "education": education,
        "experience": experience,
        "summary": base.get("summary") or f"识别到 {len(base.get('skills', []))} 个候选人技能线索。",
        "parser": base.get("parser", "rules"),
        "sensitive_info": _detect_sensitive_info(resume_text),
    }


def _skill_lookup(skills: list[str]) -> set[str]:
    return {(_normalize_skill(s) or s).lower() for s in skills if s}


def build_screening_report(job_name: str, resume_text: str = "", user_profile: list[dict] | dict | None = None, top_n: int = 20) -> dict:
    job_profile = build_job_profile(job_name, top_n=top_n)
    candidate = extract_candidate_profile(resume_text=resume_text, user_profile=user_profile)

    candidate_names = profile_to_skill_names(candidate["skills"])
    candidate_set = _skill_lookup(candidate_names)
    matched_skills = []
    missing_skills = []
    weak_evidence = []
    for skill in job_profile["hard_skills"]:
        key = (_normalize_skill(skill["name"]) or skill["name"]).lower()
        if key in candidate_set:
            matched_skills.append(skill)
        else:
            missing_skills.append(skill)
    for item in candidate["skills"]:
        if isinstance(item, dict) and item.get("skill") in job_profile["must_have"] and not item.get("evidence"):
            weak_evidence.append(item.get("skill"))

    # ── 评分维度 ──

    # 1. 技能 (max 55)
    must_total = max(1, len(job_profile["must_have"]))
    must_matched = len([s for s in matched_skills if s["name"] in job_profile["must_have"]])
    skill_score = round(must_matched / must_total * 45 + max(0, len(matched_skills) - must_matched) / max(1, len(job_profile["nice_to_have"])) * 10, 1)
    skill_score = min(skill_score, 55)

    # 2. 学历 (max 15)
    required_degree = job_profile["education_requirements"][0]["degree"] if job_profile["education_requirements"] else ""
    candidate_degree = candidate["education"].get("degree", "")
    if not required_degree:
        education_score = 15
    elif DEGREE_RANK.get(candidate_degree, 0) >= DEGREE_RANK.get(required_degree, 0):
        education_score = 15
    else:
        education_score = 5

    # 3. 专业 (max 10)
    major_required = {m["major"] for m in job_profile["major_requirements"]}
    candidate_major = candidate["education"].get("major", "")
    if not major_required:
        major_score = 10
    elif candidate_major in major_required:
        major_score = 10
    else:
        major_score = 4

    # 4. 经历 (max 15)
    exp = candidate["experience"]
    experience_score = 15
    if job_profile["experience_requirements"]:
        has_exp = exp["has_internship"] or exp["has_project"] or exp["work_experience"]
        if has_exp:
            # 有经验年限要求时，检查是否达标
            req_years = 0
            for req in job_profile["experience_requirements"]:
                m = re.search(r"(\d+)", req.get("value", ""))
                if m:
                    req_years = max(req_years, int(m.group(1)))
            if req_years > 0 and exp.get("experience_years", 0) < req_years:
                experience_score = 8  # 有经历但年限不足
            else:
                experience_score = 15
        else:
            experience_score = 4

    # 5. 证据质量 (max 10)
    if exp["metrics"]:
        evidence_score = 10
    elif exp["projects"]:
        evidence_score = 6
    else:
        evidence_score = 3

    total_score = round(skill_score + education_score + major_score + experience_score + evidence_score, 1)

    # ── 扣分原因 ──
    concerns = []
    if skill_score < 55:
        concern = {"dimension": "skills", "score": skill_score, "max": 55}
        if must_matched < must_total:
            concern["reason"] = f"必备技能覆盖 {must_matched}/{must_total}，缺口：" + "、".join(
                s["name"] for s in missing_skills if s["name"] in job_profile["must_have"]
            )[:5]
        else:
            concern["reason"] = f"加分技能覆盖不足，匹配 {len(matched_skills)}/{len(job_profile['hard_skills'])}"
        concerns.append(concern)

    if education_score < 15:
        concerns.append({
            "dimension": "education", "score": education_score, "max": 15,
            "reason": f"岗位要求{required_degree}，简历为{candidate_degree or '未明确'}",
        })

    if major_score < 10:
        concerns.append({
            "dimension": "major", "score": major_score, "max": 10,
            "reason": f"岗位要求{'、'.join(major_required)}，简历为{candidate_major or '未明确'}",
        })

    if experience_score < 15:
        reason = "经历证据不足，未明确实习/项目/工作经历"
        if experience_score == 8:
            req_years = 0
            for req in job_profile["experience_requirements"]:
                m = re.search(r"(\d+)", req.get("value", ""))
                if m:
                    req_years = max(req_years, int(m.group(1)))
            reason = f"有经历但年限不足，岗位要求{req_years}年，候选人约{exp.get('experience_years', 0)}年"
        concerns.append({"dimension": "experience", "score": experience_score, "max": 15, "reason": reason})

    if evidence_score < 10:
        concerns.append({
            "dimension": "evidence", "score": evidence_score, "max": 10,
            "reason": "简历缺少量化成果描述" if evidence_score == 3 else "有项目但缺少量化数据",
        })

    # ── 阻断项 ──
    blocking = []
    if must_matched < max(1, must_total * 0.5):
        blocking.append("必备技能覆盖不足")
    if required_degree and education_score < 15:
        blocking.append(f"学历要求可能不满足：岗位要求{required_degree}，简历未明确或低于要求")
    if major_required and major_score < 10:
        blocking.append("专业匹配度不明确")
    if job_profile["experience_requirements"] and experience_score < 15:
        blocking.append("经历证据不足，未明确实习/项目/工作经历")
    if weak_evidence:
        blocking.append("部分关键技能缺少项目证据：" + "、".join(weak_evidence[:5]))

    # ── 风险等级 ──
    if total_score >= 75 and not blocking:
        risk = "low"
    elif total_score >= 55:
        risk = "medium"
    else:
        risk = "high"

    # ── 建议 ──
    suggestions = []
    for skill in missing_skills[:5]:
        suggestions.append(f"补充或强化「{skill['name']}」相关经历，优先引用项目证据。")
    if not exp["metrics"]:
        suggestions.append("在项目经历中补充可量化成果，例如规模、效率、准确率、上线结果。")
    if major_required and major_score < 10:
        suggestions.append("如果专业不完全匹配，在简历摘要中强调相关课程、项目或证书证据。")
    if experience_score == 8:
        suggestions.append("经历年限略低于要求，可强调高质量项目经验弥补。")

    return {
        "job_profile": job_profile,
        "candidate_profile": candidate,
        "score": total_score,
        "pass_risk": risk,
        "dimension_scores": {
            "skills": skill_score,
            "education": education_score,
            "major": major_score,
            "experience": experience_score,
            "evidence": evidence_score,
        },
        "matched_points": [s["name"] for s in matched_skills],
        "missing_points": [s["name"] for s in missing_skills[:10]],
        "concerns": concerns,
        "matched_requirements": {
            "skills": matched_skills,
            "education": candidate_degree or "未明确",
            "major": candidate_major or "未明确",
        },
        "missing_requirements": {
            "skills": missing_skills,
            "education": required_degree if education_score < 15 else "",
            "major": list(major_required) if major_score < 10 else [],
        },
        "blocking_issues": blocking,
        "improvement_suggestions": suggestions[:8],
        "summary": f"初筛模拟得分 {total_score:.0f}/100，风险等级：{risk}。主要依据为必备技能覆盖、学历/专业、经历证据和项目量化程度。",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
