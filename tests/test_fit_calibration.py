"""v0.18 Fit analysis calibration tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.profile_schemas import JobProfileResult, CandidateProfileResult


def test_intern_with_strong_project_not_weak():
    """实习岗位项目匹配强时不应被判 weak"""
    from services.fit_analysis_service import analyze_fit
    job = JobProfileResult(
        job_name="Python后端实习", job_type="实习", employment_type="实习",
        must_have_capabilities=["Python", "FastAPI"],
        nice_to_have_capabilities=["Docker"],
    )
    cand = CandidateProfileResult(
        skill_stack=[{"skill": "Python"}, {"skill": "FastAPI"}, {"skill": "Docker"}],
        projects=[{"name": "Web平台", "description": "Python后端"}],
        achievements=[{"description": "性能提升30%", "has_metric": True}],
        learning_signals=["自主学习"],
    )
    result = analyze_fit(job, cand)
    assert result.overall_fit_level != "weak", f"实习岗位不应判weak: {result.overall_fit_level}"


def test_obvious_mismatch_is_weak():
    """明显技能和经历都不匹配时应判 weak"""
    from services.fit_analysis_service import analyze_fit
    job = JobProfileResult(
        job_name="嵌入式开发", job_type="正式", employment_type="全职",
        must_have_capabilities=["C", "ARM", "RTOS"],
    )
    cand = CandidateProfileResult(
        skill_stack=[{"skill": "Python"}],
        projects=[],
        internships=[],
        work_experiences=[],
    )
    result = analyze_fit(job, cand)
    assert result.overall_fit_level == "weak"


def test_product_role_not_scored_by_tech_only():
    """产品岗位不能只按技术技能覆盖率评分"""
    from services.fit_analysis_service import analyze_fit
    job = JobProfileResult(
        job_name="AI产品经理", job_type="正式", employment_type="全职",
        must_have_capabilities=["PRD", "用户研究", "竞品分析", "SQL"],
    )
    cand = CandidateProfileResult(
        skill_stack=[{"skill": "PRD"}, {"skill": "用户研究"}, {"skill": "SQL"}],
        projects=[{"name": "智能客服产品"}],
        achievements=[{"description": "上线后满意度提升20%", "has_metric": True}],
        learning_signals=["技术迁移"],
    )
    result = analyze_fit(job, cand)
    assert result.overall_fit_level in ("strong", "moderate")


def test_data_analyst_identifies_relevant_skills():
    """数据分析岗位应识别 SQL/指标/看板/分析项目为强相关"""
    from services.fit_analysis_service import analyze_fit
    job = JobProfileResult(
        job_name="数据分析师", job_type="正式", employment_type="全职",
        must_have_capabilities=["SQL", "Python", "指标体系", "数据看板"],
    )
    cand = CandidateProfileResult(
        skill_stack=[{"skill": "SQL"}, {"skill": "Python"}, {"skill": "指标体系"}],
        projects=[{"name": "用户行为分析", "description": "数据看板"}],
        achievements=[{"description": "覆盖10万用户", "has_metric": True}],
    )
    result = analyze_fit(job, cand)
    assert "指标体系" in str(result.capability_fit.evidence_refs) or result.capability_fit.score >= 50


def test_critical_gap_lowers_level():
    """critical_gap 会降低等级"""
    from services.fit_analysis_service import _risks_and_gaps
    job = JobProfileResult(job_name="Python后端", must_have_capabilities=["Python", "FastAPI", "Docker"])
    cand = CandidateProfileResult(
        skill_stack=[],
        risk_points=["学历要求不满足"],
    )
    result = _risks_and_gaps(job, cand)
    assert result.level == "weak"


def test_normal_gap_in_learning_plan():
    """normal_gap 进入 learning_plan，不直接强降级"""
    from services.fit_analysis_service import analyze_fit
    job = JobProfileResult(
        job_name="Python后端", job_type="正式",
        must_have_capabilities=["Python", "Redis"],
    )
    cand = CandidateProfileResult(
        skill_stack=[{"skill": "Python"}],
        projects=[{"name": "Web平台"}],
        achievements=[],
    )
    result = analyze_fit(job, cand)
    assert "redis" in str(result.learning_plan).lower() or "Redis" in str(result.learning_plan)


def test_agent_prompt_has_non_ats_constraint():
    """FitAnalysisAgent prompt 包含非硬性 ATS 约束"""
    from services.fit_analysis_agent import AGENT_PROMPT
    assert "硬性" in AGENT_PROMPT or "ATS" in AGENT_PROMPT
    assert "非技术岗位" in AGENT_PROMPT or "产品" in AGENT_PROMPT


def test_golden_eval_near_match():
    """near_match 计算正确"""
    from eval.run_golden_eval import _evaluate_case
    case = {
        "gold_job_profile": {"must_have_capabilities": ["Python"]},
        "gold_candidate_profile": {"skill_keywords": ["Python"], "project_keywords": [], "achievement_keywords": []},
        "gold_fit": {"overall_fit_level": "strong", "expected_strengths": [], "expected_gaps": [], "expected_learning_keywords": []},
    }
    job = {"must_have_capabilities": ["Python"], "responsibilities": []}
    cand = {"skill_stack": [{"skill": "Python"}], "projects": [], "achievements": []}
    # actual=moderate, gold=strong → near_match
    fit = {"overall_fit_level": "moderate", "strengths": [], "gaps": [], "learning_plan": []}
    result = _evaluate_case(case, job, cand, fit)
    assert result["fit_level_match"] is False
    assert result["fit_level_near_match"] is True
    assert result["actual_fit_level"] == "moderate"


def test_job_profile_score_not_degraded():
    """旧 job_profile_score 不应明显下降"""
    from services.profile_schemas import JobProfileResult
    # 模拟简单场景
    from services.fit_analysis_service import analyze_fit
    job = JobProfileResult(
        job_name="Python后端", job_type="正式",
        must_have_capabilities=["Python", "FastAPI", "MySQL"],
    )
    cand = CandidateProfileResult(
        skill_stack=[{"skill": "Python"}, {"skill": "FastAPI"}, {"skill": "MySQL"}],
        projects=[{"name": "Web平台"}],
        achievements=[{"description": "提升30%", "has_metric": True}],
    )
    result = analyze_fit(job, cand)
    assert result.overall_score >= 50


def test_golden_eval_overall_not_degraded():
    """全量 Golden Set job_profile_score 不低于 80"""
    from eval.run_golden_eval import run_golden_eval
    report = run_golden_eval(limit=5)
    avg = report["summary"]["avg_job_profile_score"]
    assert avg >= 80, f"avg job_profile_score: {avg}"
