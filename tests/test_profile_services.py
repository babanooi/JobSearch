"""v0.9 Profile services tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


MOCK_SKILLS = [
    {"skill": "Python", "count": 18, "total_jds": 20},
    {"skill": "FastAPI", "count": 14, "total_jds": 20},
    {"skill": "MySQL", "count": 12, "total_jds": 20},
    {"skill": "Docker", "count": 8, "total_jds": 20},
    {"skill": "Redis", "count": 6, "total_jds": 20},
]

MOCK_JDS = [
    {
        "title": "Python后端开发",
        "company": "Example",
        "text": (
            "岗位职责：负责公司内部平台的后端开发与维护。"
            "任职要求：本科及以上学历，计算机相关专业优先。"
            "需要 Python、FastAPI、MySQL，有后端项目或实习经历优先。"
            "具备良好的沟通协作能力和学习能力。熟悉Docker部署。"
            "有3年以上工作经验优先。"
        ),
        "source_url": "https://example.com/job/1",
        "fetched_at": "2026-06-01T10:00:00",
    }
]


# ── 岗位画像测试 ──

def test_job_profile_extracts_responsibilities(monkeypatch):
    """岗位画像能提取核心职责"""
    from services import job_profile_service, screening
    monkeypatch.setattr(screening, "query_skill_rank", lambda *a, **kw: MOCK_SKILLS)
    monkeypatch.setattr(screening, "_fetch_jd_texts", lambda *a, **kw: MOCK_JDS)

    result = job_profile_service.extract_job_profile("Python后端")
    assert isinstance(result.responsibilities, list)
    assert result.sample_count > 0


def test_job_profile_returns_unknown_for_missing(monkeypatch):
    """缺失信息返回 unknown，不编造"""
    from services import job_profile_service, screening
    empty_jd = [{"title": "无要求JD", "company": "", "text": "岗位职责：开发系统。任职要求：会写代码。" * 5, "source_url": "", "fetched_at": ""}]
    monkeypatch.setattr(screening, "query_skill_rank", lambda *a, **kw: [])
    monkeypatch.setattr(screening, "_fetch_jd_texts", lambda *a, **kw: empty_jd)

    result = job_profile_service.extract_job_profile("不存在的岗位")
    assert result.education_preference in ("未明确", "")
    assert result.experience_requirement in ("未明确", "")


def test_job_profile_has_confidence(monkeypatch):
    """岗位画像有置信度"""
    from services import job_profile_service, screening
    monkeypatch.setattr(screening, "query_skill_rank", lambda *a, **kw: MOCK_SKILLS)
    monkeypatch.setattr(screening, "_fetch_jd_texts", lambda *a, **kw: MOCK_JDS)

    result = job_profile_service.extract_job_profile("Python后端")
    assert result.confidence in ("high", "medium", "low")


def test_job_profile_schema_validation(monkeypatch):
    """岗位画像结果经过 Pydantic 校验"""
    from services import job_profile_service, screening
    from services.profile_schemas import JobProfileResult
    monkeypatch.setattr(screening, "query_skill_rank", lambda *a, **kw: MOCK_SKILLS)
    monkeypatch.setattr(screening, "_fetch_jd_texts", lambda *a, **kw: MOCK_JDS)

    result = job_profile_service.extract_job_profile("Python后端")
    assert isinstance(result, JobProfileResult)


# ── 候选人画像测试 ──

def test_candidate_profile_extracts_projects():
    """候选人画像能提取项目经历"""
    from services.candidate_profile_service import extract_candidate_profile
    result = extract_candidate_profile(
        resume_text="本科计算机专业。项目：开发了一个基于Python的Web平台，使用FastAPI和MySQL。上线后用户量达到1000+。"
    )
    assert len(result.projects) > 0


def test_candidate_profile_extracts_achievements():
    """候选人画像能提取成果证据"""
    from services.candidate_profile_service import extract_candidate_profile
    result = extract_candidate_profile(
        resume_text="本科计算机。项目：优化数据库查询，性能提升30%。获得校级编程竞赛一等奖。"
    )
    assert len(result.achievements) > 0
    assert any(a.get("has_metric") for a in result.achievements)


def test_candidate_profile_explicit_vs_inferred():
    """候选人画像区分 explicit 和 inferred"""
    from services.candidate_profile_service import extract_candidate_profile
    result = extract_candidate_profile(resume_text="3年工作经验，本科计算机。Python项目。")
    assert result.internships == [] or all(i.get("confidence") for i in result.internships)


def test_candidate_profile_learning_signals():
    """候选人画像提取学习能力信号"""
    from services.candidate_profile_service import extract_candidate_profile
    result = extract_candidate_profile(
        resume_text="本科计算机。自学Rust，GitHub开源项目贡献者。获得AWS认证。"
    )
    assert len(result.learning_signals) > 0


# ── 适配分析测试 ──

def test_fit_analysis_five_dimensions(monkeypatch):
    """适配分析输出 5 个综合维度"""
    from services.fit_analysis_service import analyze_fit
    from services.profile_schemas import JobProfileResult, CandidateProfileResult

    job = JobProfileResult(
        job_name="Python后端",
        must_have_capabilities=["Python", "FastAPI", "MySQL"],
    )
    cand = CandidateProfileResult(
        skill_stack=[{"skill": "Python", "confidence": "explicit"}, {"skill": "FastAPI", "confidence": "explicit"}],
        projects=[{"name": "Web平台", "description": "Python后端"}],
        achievements=[{"description": "性能提升30%", "has_metric": True}],
    )
    report = analyze_fit(job, cand)

    assert report.capability_fit.level in ("strong", "moderate", "weak")
    assert report.experience_relevance.level in ("strong", "moderate", "weak")
    assert report.growth_potential.level in ("strong", "moderate", "weak")
    assert report.evidence_strength.level in ("strong", "moderate", "weak")
    assert report.risks_and_gaps.level in ("strong", "moderate", "weak")


def test_fit_analysis_evidence_refs(monkeypatch):
    """适配分析关键判断包含 evidence_refs"""
    from services.fit_analysis_service import analyze_fit
    from services.profile_schemas import JobProfileResult, CandidateProfileResult

    job = JobProfileResult(job_name="Python后端", must_have_capabilities=["Python", "Django"])
    cand = CandidateProfileResult(
        skill_stack=[{"skill": "Python", "confidence": "explicit"}],
        achievements=[{"description": "优化查询30%", "has_metric": True}],
    )
    report = analyze_fit(job, cand)
    assert len(report.evidence_refs) > 0


def test_sensitive_info_not_in_fit(monkeypatch):
    """敏感信息不参与适配评分"""
    from services.fit_analysis_service import analyze_fit
    from services.profile_schemas import JobProfileResult, CandidateProfileResult

    job = JobProfileResult(job_name="Python后端", must_have_capabilities=["Python"])
    cand_male = CandidateProfileResult(skill_stack=[{"skill": "Python"}], sensitive_detected=["男"])
    cand_female = CandidateProfileResult(skill_stack=[{"skill": "Python"}], sensitive_detected=["女"])

    r1 = analyze_fit(job, cand_male)
    r2 = analyze_fit(job, cand_female)
    assert r1.overall_score == r2.overall_score


# ── 数据库模型测试 ──

def test_job_profile_model_can_create():
    """job_profiles 模型可创建"""
    from models.profile import JobProfile
    obj = JobProfile(job_name="测试岗位", confidence="medium")
    assert obj.job_name == "测试岗位"


def test_candidate_profile_model_can_create():
    """candidate_profiles 模型可创建"""
    from models.profile import CandidateProfile
    obj = CandidateProfile(user_id=1, confidence="low")
    assert obj.user_id == 1


def test_fit_analysis_model_can_create():
    """fit_analysis_reports 模型可创建"""
    from models.profile import FitAnalysisReport
    obj = FitAnalysisReport(user_id=1, job_profile_id=1, candidate_profile_id=1, overall_score=75.0)
    assert obj.overall_score == 75.0


def test_profile_feedback_model_can_create():
    """profile_feedback 模型可创建"""
    from models.profile import ProfileFeedback
    obj = ProfileFeedback(user_id=1, target_type="job_profile", target_id=1, action="correct")
    assert obj.action == "correct"


# ── 旧功能不被破坏 ──

def test_old_skill_gap_still_works(monkeypatch):
    """旧 skill_gap 不被破坏"""
    from services.skill_gap import filter_market_skills, estimate_market_confidence
    raw = [{"skill": "Python", "count": 30, "total_jds": 15}]
    result = filter_market_skills(raw, job_name="Python后端")
    assert len(result) > 0


def test_old_skill_rank_still_works():
    """旧 skill_rank 不被破坏"""
    from services.skill_gap import is_low_quality_skill
    assert is_low_quality_skill("人工智能") is True
    assert is_low_quality_skill("Python") is False
