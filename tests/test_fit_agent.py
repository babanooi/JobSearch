"""v0.10 FitAnalysisAgent tests — monkeypatch LLM, no real API calls."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from services.profile_schemas import (
    JobProfileResult, CandidateProfileResult, FitAnalysisResult, DimensionResult,
)

MOCK_AGENT_OUTPUT = json.dumps({
    "overall_fit_level": "moderate",
    "overall_score": 68.5,
    "fit_summary": "候选人技能匹配度较高，但缺少量化成果和深度项目经验。",
    "capability_fit": {"level": "moderate", "score": 70, "summary": "匹配Python和FastAPI，缺Docker", "evidence_refs": ["匹配: Python, FastAPI"]},
    "experience_relevance": {"level": "weak", "score": 40, "summary": "只有1个项目，无实习", "evidence_refs": ["项目: Web平台"]},
    "growth_potential": {"level": "strong", "score": 80, "summary": "自学能力强，有开源贡献", "evidence_refs": ["开源参与"]},
    "evidence_strength": {"level": "moderate", "score": 55, "summary": "有量化成果但偏少", "evidence_refs": ["优化查询30%"]},
    "risks_and_gaps": {"level": "moderate", "score": 50, "summary": "Docker缺口，实习经历缺失", "evidence_refs": ["缺Docker"]},
    "strengths": ["技能覆盖Python核心栈", "学习能力信号强"],
    "gaps": ["缺少Docker部署经验", "缺少实习经历"],
    "transferable_strengths": ["团队协作"],
    "learning_plan": ["补充Docker容器化经验", "准备项目STAR描述"],
    "interview_strategy": ["重点准备技术深度问题", "突出学习能力"],
    "evidence_refs": ["匹配: Python, FastAPI", "项目: Web平台"],
    "confidence": "medium",
})

MOCK_JOB = JobProfileResult(
    job_name="Python后端",
    must_have_capabilities=["Python", "FastAPI", "Docker"],
    nice_to_have=["Redis", "MySQL"],
    experience_requirement="2年以上",
    education_preference="本科",
)
MOCK_CAND = CandidateProfileResult(
    skill_stack=[{"skill": "Python"}, {"skill": "FastAPI"}],
    projects=[{"name": "Web平台", "description": "Python后端"}],
    achievements=[{"description": "优化查询30%", "has_metric": True}],
    learning_signals=["开源参与", "自主学习"],
    risk_points=["缺少Docker经验"],
    confidence="medium",
)


def _mock_llm_with(output: str):
    """Create a mock LLM that returns the given output."""
    class MockLLM:
        def invoke(self, prompt):
            class R:
                content = output
            return R()
    return MockLLM()


def test_agent_parses_valid_json(monkeypatch):
    """Agent 成功解析合法 JSON"""
    from services import fit_analysis_agent
    monkeypatch.setattr(fit_analysis_agent, "get_utility_llm", lambda: _mock_llm_with(MOCK_AGENT_OUTPUT))

    result, mode = fit_analysis_agent.analyze_fit_with_agent(MOCK_JOB, MOCK_CAND)
    assert mode == "agent"
    assert isinstance(result, FitAnalysisResult)
    assert result.overall_fit_level == "moderate"
    assert 60 <= result.overall_score <= 70


def test_agent_has_five_dimensions(monkeypatch):
    """Agent 输出必须包含 5 个综合维度"""
    from services import fit_analysis_agent
    monkeypatch.setattr(fit_analysis_agent, "get_utility_llm", lambda: _mock_llm_with(MOCK_AGENT_OUTPUT))

    result, _ = fit_analysis_agent.analyze_fit_with_agent(MOCK_JOB, MOCK_CAND)
    assert result.capability_fit.level in ("strong", "moderate", "weak")
    assert result.experience_relevance.level in ("strong", "moderate", "weak")
    assert result.growth_potential.level in ("strong", "moderate", "weak")
    assert result.evidence_strength.level in ("strong", "moderate", "weak")
    assert result.risks_and_gaps.level in ("strong", "moderate", "weak")


def test_agent_evidence_refs_present(monkeypatch):
    """Agent 关键判断包含 evidence_refs"""
    from services import fit_analysis_agent
    monkeypatch.setattr(fit_analysis_agent, "get_utility_llm", lambda: _mock_llm_with(MOCK_AGENT_OUTPUT))

    result, _ = fit_analysis_agent.analyze_fit_with_agent(MOCK_JOB, MOCK_CAND)
    assert len(result.evidence_refs) > 0


def test_agent_fallback_on_invalid_json(monkeypatch):
    """LLM 返回非法 JSON 时 fallback 到 rule_report"""
    from services import fit_analysis_agent
    monkeypatch.setattr(fit_analysis_agent, "get_utility_llm", lambda: _mock_llm_with("这不是JSON，是自然语言回复。"))

    rule = FitAnalysisResult(overall_score=55, overall_fit_level="moderate")
    result, mode = fit_analysis_agent.analyze_fit_with_agent(MOCK_JOB, MOCK_CAND, rule_report=rule)
    assert mode == "rule_fallback"
    assert result.overall_score == 55


def test_agent_fallback_on_schema_mismatch(monkeypatch):
    """LLM 输出 schema 不合法时 fallback"""
    from services import fit_analysis_agent
    bad_output = json.dumps({"overall_fit_level": "impossible", "overall_score": 999})
    monkeypatch.setattr(fit_analysis_agent, "get_utility_llm", lambda: _mock_llm_with(bad_output))

    rule = FitAnalysisResult(overall_score=42, overall_fit_level="weak")
    result, mode = fit_analysis_agent.analyze_fit_with_agent(MOCK_JOB, MOCK_CAND, rule_report=rule)
    assert mode == "rule_fallback"
    assert result.overall_score == 42


def test_agent_fallback_on_llm_exception(monkeypatch):
    """LLM 调用异常时 fallback"""
    from services import fit_analysis_agent
    class BrokenLLM:
        def invoke(self, prompt):
            raise RuntimeError("API 超时")
    monkeypatch.setattr(fit_analysis_agent, "get_utility_llm", lambda: BrokenLLM())

    rule = FitAnalysisResult(overall_score=33, overall_fit_level="weak")
    result, mode = fit_analysis_agent.analyze_fit_with_agent(MOCK_JOB, MOCK_CAND, rule_report=rule)
    assert mode == "rule_fallback"
    assert result.overall_score == 33


def test_agent_ignores_sensitive_info(monkeypatch):
    """敏感信息不参与评分"""
    from services import fit_analysis_agent
    monkeypatch.setattr(fit_analysis_agent, "get_utility_llm", lambda: _mock_llm_with(MOCK_AGENT_OUTPUT))

    cand_male = CandidateProfileResult(
        skill_stack=[{"skill": "Python"}],
        sensitive_detected=["男", "年龄"],
    )
    cand_female = CandidateProfileResult(
        skill_stack=[{"skill": "Python"}],
        sensitive_detected=["女", "年龄"],
    )
    r1, _ = fit_analysis_agent.analyze_fit_with_agent(MOCK_JOB, cand_male)
    r2, _ = fit_analysis_agent.analyze_fit_with_agent(MOCK_JOB, cand_female)
    assert r1.overall_score == r2.overall_score


def test_rule_still_works_independently():
    """旧 analyze_fit() 规则逻辑仍可单独使用"""
    from services.fit_analysis_service import analyze_fit
    result = analyze_fit(MOCK_JOB, MOCK_CAND)
    assert isinstance(result, FitAnalysisResult)
    assert result.overall_score > 0
    assert result.capability_fit.level in ("strong", "moderate", "weak")


def test_old_skill_gap_not_broken():
    """旧 skill_gap 不被破坏"""
    from services.skill_gap import filter_market_skills, estimate_market_confidence
    raw = [{"skill": "Python", "count": 30, "total_jds": 15}]
    result = filter_market_skills(raw, job_name="Python后端")
    assert len(result) > 0
    conf = estimate_market_confidence(result, raw_count=1, total_jds=15)
    assert conf["confidence"] in ("high", "medium", "low")
