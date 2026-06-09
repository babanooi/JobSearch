"""Fit analysis service — v0.9 综合适配评估"""
from __future__ import annotations
import json
from datetime import datetime
from services.profile_schemas import (
    JobProfileResult, CandidateProfileResult, FitAnalysisResult, DimensionResult,
)
from core.logger import get_logger

logger = get_logger(__name__)


def _capability_fit(job: JobProfileResult, cand: CandidateProfileResult) -> DimensionResult:
    """能力匹配度"""
    must = set(s.lower() for s in job.must_have_capabilities)
    cand_skills = set(s["skill"].lower() for s in cand.skill_stack)
    matched = must & cand_skills
    missing = must - cand_skills
    ratio = len(matched) / max(1, len(must))

    if ratio >= 0.7:
        level = "strong"
    elif ratio >= 0.4:
        level = "moderate"
    else:
        level = "weak"

    refs = [f"匹配: {', '.join(list(matched)[:5])}"] if matched else []
    if missing:
        refs.append(f"缺口: {', '.join(list(missing)[:5])}")

    return DimensionResult(
        level=level,
        score=round(ratio * 100, 1),
        summary=f"必备技能覆盖 {len(matched)}/{len(must)}",
        evidence_refs=refs,
    )


def _experience_relevance(job: JobProfileResult, cand: CandidateProfileResult) -> DimensionResult:
    """经历相关性"""
    has_exp = bool(cand.projects or cand.internships or cand.work_experiences)
    project_count = len(cand.projects)
    intern_count = len(cand.internships)
    work_count = len(cand.work_experiences)
    total = project_count + intern_count + work_count

    if total >= 3 and has_exp:
        level = "strong"
    elif total >= 1:
        level = "moderate"
    else:
        level = "weak"

    refs = []
    if cand.projects:
        refs.append(f"项目: {cand.projects[0].get('name', '')[:30]}")
    if cand.internships:
        refs.append(f"实习: {cand.internships[0].get('description', '')[:50]}")

    return DimensionResult(
        level=level,
        score=min(100, total * 25),
        summary=f"项目{project_count}个、实习{intern_count}段、工作{work_count}段",
        evidence_refs=refs,
    )


def _growth_potential(job: JobProfileResult, cand: CandidateProfileResult) -> DimensionResult:
    """成长潜力"""
    signals = cand.learning_signals + cand.transferable_strengths
    score = min(100, len(signals) * 20)

    if len(signals) >= 4:
        level = "strong"
    elif len(signals) >= 2:
        level = "moderate"
    else:
        level = "weak"

    return DimensionResult(
        level=level,
        score=score,
        summary=f"学习信号: {', '.join(signals[:3])}" if signals else "未识别到学习能力信号",
        evidence_refs=signals[:5],
    )


def _evidence_strength(cand: CandidateProfileResult) -> DimensionResult:
    """证据充分度"""
    metrics = [a for a in cand.achievements if a.get("has_metric")]
    achievements_count = len(cand.achievements)
    has_metrics = len(metrics) > 0

    if has_metrics and achievements_count >= 3:
        level = "strong"
    elif achievements_count >= 1:
        level = "moderate"
    else:
        level = "weak"

    refs = [a.get("description", "")[:60] for a in cand.achievements[:3]]

    return DimensionResult(
        level=level,
        score=min(100, achievements_count * 20 + (30 if has_metrics else 0)),
        summary=f"{achievements_count} 个成果证据，{'含' if has_metrics else '无'}量化数据",
        evidence_refs=refs,
    )


def _risks_and_gaps(job: JobProfileResult, cand: CandidateProfileResult) -> DimensionResult:
    """风险与短板"""
    risks = list(cand.risk_points)
    must = set(s.lower() for s in job.must_have_capabilities)
    cand_skills = set(s["skill"].lower() for s in cand.skill_stack)
    missing = must - cand_skills
    if missing:
        risks.append(f"必备技能缺口: {', '.join(list(missing)[:5])}")

    level = "weak" if len(risks) >= 3 else "moderate" if len(risks) >= 1 else "strong"
    score = max(0, 100 - len(risks) * 20)

    return DimensionResult(
        level=level,
        score=score,
        summary=f"{len(risks)} 个风险点",
        evidence_refs=risks[:5],
    )


def analyze_fit(
    job_profile: JobProfileResult,
    candidate_profile: CandidateProfileResult,
) -> FitAnalysisResult:
    """综合适配分析"""
    cap = _capability_fit(job_profile, candidate_profile)
    exp = _experience_relevance(job_profile, candidate_profile)
    growth = _growth_potential(job_profile, candidate_profile)
    evidence = _evidence_strength(candidate_profile)
    risks = _risks_and_gaps(job_profile, candidate_profile)

    # 综合分
    overall = round(
        cap.score * 0.35 +
        exp.score * 0.25 +
        growth.score * 0.15 +
        evidence.score * 0.15 +
        risks.score * 0.10,
        1
    )

    if overall >= 75 and cap.level != "weak":
        fit_level = "strong"
    elif overall >= 45:
        fit_level = "moderate"
    else:
        fit_level = "weak"

    # 优势
    strengths = []
    if cap.level == "strong":
        strengths.append(f"技能匹配度高，覆盖必备技能")
    if exp.level == "strong":
        strengths.append("项目/实习经历丰富")
    if growth.level == "strong":
        strengths.append("学习能力信号强")
    if evidence.level == "strong":
        strengths.append("成果证据充分")

    # 差距
    gaps = []
    must = set(s.lower() for s in job_profile.must_have_capabilities)
    cand_skills = set(s["skill"].lower() for s in candidate_profile.skill_stack)
    missing = must - cand_skills
    if missing:
        gaps.append(f"必备技能缺口: {', '.join(list(missing)[:5])}")
    if not candidate_profile.projects:
        gaps.append("缺少项目经历")
    if not candidate_profile.achievements:
        gaps.append("缺少量化成果")

    # 可迁移优势
    transferable = candidate_profile.transferable_strengths[:5]

    # 学习计划
    learning_plan = []
    for skill in list(missing)[:5]:
        learning_plan.append(f"补充「{skill}」相关技能和项目经验")

    # 面试策略
    interview_strategy = []
    if cap.level != "weak":
        interview_strategy.append("重点准备技术深度问题")
    if exp.level != "weak":
        interview_strategy.append("准备项目经历 STAR 描述")
    if growth.level == "strong":
        interview_strategy.append("突出学习能力和技术热情")

    # 综合置信度
    conf = job_profile.confidence if job_profile.confidence == candidate_profile.confidence else "medium"

    return FitAnalysisResult(
        overall_fit_level=fit_level,
        overall_score=overall,
        fit_summary=f"综合适配 {fit_level}（{overall}分）：能力匹配{cap.level}、经历相关{exp.level}、成长潜力{growth.level}、证据{evidence.level}、风险{risks.level}",
        capability_fit=cap,
        experience_relevance=exp,
        growth_potential=growth,
        evidence_strength=evidence,
        risks_and_gaps=risks,
        strengths=strengths,
        gaps=gaps,
        transferable_strengths=transferable,
        learning_plan=learning_plan,
        interview_strategy=interview_strategy,
        evidence_refs=(cap.evidence_refs + exp.evidence_refs + evidence.evidence_refs)[:10],
        confidence=conf,
    )


def save_fit_analysis(
    result: FitAnalysisResult,
    user_id: int,
    job_profile_id: int,
    candidate_profile_id: int,
) -> int:
    """保存适配分析报告到数据库"""
    from models.database import SessionLocal
    from models.profile import FitAnalysisReport
    with SessionLocal() as session:
        obj = FitAnalysisReport(
            user_id=user_id,
            job_profile_id=job_profile_id,
            candidate_profile_id=candidate_profile_id,
            overall_fit_level=result.overall_fit_level,
            overall_score=result.overall_score,
            fit_summary=result.fit_summary,
            capability_fit=json.dumps(result.capability_fit.model_dump(), ensure_ascii=False),
            experience_relevance=json.dumps(result.experience_relevance.model_dump(), ensure_ascii=False),
            growth_potential=json.dumps(result.growth_potential.model_dump(), ensure_ascii=False),
            evidence_strength=json.dumps(result.evidence_strength.model_dump(), ensure_ascii=False),
            risks_and_gaps=json.dumps(result.risks_and_gaps.model_dump(), ensure_ascii=False),
            strengths=json.dumps(result.strengths, ensure_ascii=False),
            gaps=json.dumps(result.gaps, ensure_ascii=False),
            transferable_strengths=json.dumps(result.transferable_strengths, ensure_ascii=False),
            learning_plan=json.dumps(result.learning_plan, ensure_ascii=False),
            interview_strategy=json.dumps(result.interview_strategy, ensure_ascii=False),
            evidence_refs=json.dumps(result.evidence_refs, ensure_ascii=False),
            confidence=result.confidence,
        )
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.id
