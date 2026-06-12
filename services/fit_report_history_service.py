"""Fit report history service — v0.22"""
from __future__ import annotations
import json
from datetime import datetime
from core.logger import get_logger

logger = get_logger(__name__)


def list_fit_reports(
    user_id: int = 0,
    job_name: str = "",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """查询用户历史适配报告，返回 (items, total)"""
    from models.database import SessionLocal
    from models.profile import FitAnalysisReport, JobProfile
    with SessionLocal() as session:
        q = session.query(FitAnalysisReport)
        if user_id:
            q = q.filter(FitAnalysisReport.user_id == user_id)
        if job_name:
            # 通过 job_profile_id 关联 job_name
            jp_ids = session.query(JobProfile.id).filter(
                JobProfile.job_name == job_name
            ).all()
            jp_id_set = {r[0] for r in jp_ids}
            if jp_id_set:
                q = q.filter(FitAnalysisReport.job_profile_id.in_(jp_id_set))
            else:
                return [], 0
        total = q.count()
        rows = q.order_by(FitAnalysisReport.created_at.desc()).offset(offset).limit(limit).all()

        items = []
        for r in rows:
            # 取 job_name
            jp = session.get(JobProfile, r.job_profile_id)
            job_name_val = jp.job_name if jp else ""
            items.append({
                "id": r.id,
                "user_id": r.user_id,
                "job_profile_id": r.job_profile_id,
                "candidate_profile_id": r.candidate_profile_id,
                "job_name": job_name_val,
                "overall_fit_level": r.overall_fit_level,
                "overall_score": r.overall_score,
                "confidence": r.confidence,
                "fit_summary": r.fit_summary,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            })

    return items, total


def delete_fit_report(report_id: int, user_id: int = 0) -> bool:
    """删除指定报告。user_id>0 时校验只能删自己的。"""
    from models.database import SessionLocal
    from models.profile import FitAnalysisReport
    with SessionLocal() as session:
        obj = session.get(FitAnalysisReport, report_id)
        if not obj:
            return False
        if user_id and obj.user_id != user_id:
            return False
        session.delete(obj)
        session.commit()
        logger.info(f"删除适配报告: id={report_id}")
    return True


def rerun_fit_report(report_id: int, user_id: int = 0) -> dict | None:
    """基于历史报告的 job_profile_id / candidate_profile_id 重新生成报告，保存为新记录。"""
    from models.database import SessionLocal
    from models.profile import FitAnalysisReport, JobProfile, CandidateProfile
    from services.fit_analysis_service import analyze_fit
    from services.profile_schemas import JobProfileResult, CandidateProfileResult

    with SessionLocal() as session:
        old = session.get(FitAnalysisReport, report_id)
        if not old:
            return None
        if user_id and old.user_id != user_id:
            return None

        jp = session.get(JobProfile, old.job_profile_id)
        cp = session.get(CandidateProfile, old.candidate_profile_id)
        if not jp or not cp:
            return None

        import json as _json
        job_result = JobProfileResult(
            job_name=jp.job_name,
            job_type=jp.job_type or "",
            employment_type=jp.employment_type or "",
            target_audience=jp.target_audience or "",
            responsibilities=_json.loads(jp.responsibilities) if jp.responsibilities else [],
            must_have_capabilities=_json.loads(jp.must_have_capabilities) if jp.must_have_capabilities else [],
            nice_to_have_capabilities=_json.loads(jp.nice_to_have_capabilities) if jp.nice_to_have_capabilities else [],
            experience_requirement=jp.experience_requirement or "",
            education_preference=jp.education_preference or "",
            major_preference=jp.major_preference or "",
            business_context=_json.loads(jp.business_context) if jp.business_context else [],
            growth_context=_json.loads(jp.growth_context) if jp.growth_context else [],
            confidence=jp.confidence or "low",
            sample_count=jp.sample_count,
        )
        cand_result = CandidateProfileResult(
            education_background=_json.loads(cp.education_background) if cp.education_background else {},
            skill_stack=_json.loads(cp.skill_stack) if cp.skill_stack else [],
            projects=_json.loads(cp.projects) if cp.projects else [],
            internships=_json.loads(cp.internships) if cp.internships else [],
            work_experiences=_json.loads(cp.work_experiences) if cp.work_experiences else [],
            business_understanding=_json.loads(cp.business_understanding) if cp.business_understanding else [],
            achievements=_json.loads(cp.achievements) if cp.achievements else [],
            learning_signals=_json.loads(cp.learning_signals) if cp.learning_signals else [],
            transferable_strengths=_json.loads(cp.transferable_strengths) if cp.transferable_strengths else [],
            collaboration_signals=_json.loads(cp.collaboration_signals) if cp.collaboration_signals else [],
            risk_points=_json.loads(cp.risk_points) if cp.risk_points else [],
            confidence=cp.confidence or "low",
            sensitive_detected=_json.loads(cp.sensitive_detected) if cp.sensitive_detected else [],
        )

    # 在 session 外调用 fit analysis（可能调 LLM）
    new_report = analyze_fit(job_result, cand_result)

    # 保存为新记录
    with SessionLocal() as session:
        obj = FitAnalysisReport(
            user_id=old.user_id,
            job_profile_id=old.job_profile_id,
            candidate_profile_id=old.candidate_profile_id,
            overall_fit_level=new_report.overall_fit_level,
            overall_score=new_report.overall_score,
            fit_summary=new_report.fit_summary,
            capability_fit=json.dumps(new_report.capability_fit.model_dump(), ensure_ascii=False),
            experience_relevance=json.dumps(new_report.experience_relevance.model_dump(), ensure_ascii=False),
            growth_potential=json.dumps(new_report.growth_potential.model_dump(), ensure_ascii=False),
            evidence_strength=json.dumps(new_report.evidence_strength.model_dump(), ensure_ascii=False),
            risks_and_gaps=json.dumps(new_report.risks_and_gaps.model_dump(), ensure_ascii=False),
            strengths=json.dumps(new_report.strengths, ensure_ascii=False),
            gaps=json.dumps(new_report.gaps, ensure_ascii=False),
            transferable_strengths=json.dumps(new_report.transferable_strengths, ensure_ascii=False),
            learning_plan=json.dumps(new_report.learning_plan, ensure_ascii=False),
            interview_strategy=json.dumps(new_report.interview_strategy, ensure_ascii=False),
            evidence_refs=json.dumps(new_report.evidence_refs, ensure_ascii=False),
            confidence=new_report.confidence,
        )
        session.add(obj)
        session.commit()
        session.refresh(obj)
        logger.info(f"重跑适配报告: 旧id={report_id} → 新id={obj.id}")
        return {"id": obj.id, "report": new_report.model_dump()}
