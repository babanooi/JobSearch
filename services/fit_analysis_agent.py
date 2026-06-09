"""Fit Analysis Agent — v0.10 规则信号 + LLM 综合适配分析"""
from __future__ import annotations
import json
import re
from typing import Optional
from services.profile_schemas import (
    JobProfileResult, CandidateProfileResult, FitAnalysisResult, DimensionResult,
)
from services.fit_analysis_service import analyze_fit
from agents.base import get_utility_llm
from core.logger import get_logger

logger = get_logger(__name__)

AGENT_PROMPT = """你是求职适配分析 Agent。你的任务不是硬性 ATS 打分，而是综合判断候选人与岗位的适配度。

## 规则
1. 只能基于输入的画像和证据判断，不得编造信息。
2. 没有证据支撑的判断要降低 confidence。
3. **禁止**使用年龄、性别、民族、婚育、外貌等敏感信息作为判断依据。
4. 输出必须是纯 JSON，不要输出 Markdown 或任何其他格式。
5. 每个维度必须包含 level（strong/moderate/weak）、score（0-100）、summary、evidence_refs。

## 输入

### 岗位画像
{job_profile}

### 候选人画像
{candidate_profile}

### 规则信号（参考，不要简单复制）
{rule_signals}

## 输出 JSON 格式
{{
  "overall_fit_level": "strong/moderate/weak",
  "overall_score": 0-100,
  "fit_summary": "综合判断说明",
  "capability_fit": {{"level":"strong/moderate/weak","score":0-100,"summary":"说明","evidence_refs":["..."]}},
  "experience_relevance": {{"level":"strong/moderate/weak","score":0-100,"summary":"说明","evidence_refs":["..."]}},
  "growth_potential": {{"level":"strong/moderate/weak","score":0-100,"summary":"说明","evidence_refs":["..."]}},
  "evidence_strength": {{"level":"strong/moderate/weak","score":0-100,"summary":"说明","evidence_refs":["..."]}},
  "risks_and_gaps": {{"level":"strong/moderate/weak","score":0-100,"summary":"说明","evidence_refs":["..."]}},
  "strengths": ["优势1", "优势2"],
  "gaps": ["差距1", "差距2"],
  "transferable_strengths": ["可迁移优势1"],
  "learning_plan": ["学习建议1", "学习建议2"],
  "interview_strategy": ["面试策略1"],
  "evidence_refs": ["证据1", "证据2"],
  "confidence": "high/medium/low"
}}

只输出 JSON。"""


def _build_rule_signals(rule_report: Optional[FitAnalysisResult]) -> str:
    """将规则报告转为 LLM 可读的信号文本"""
    if not rule_report:
        return "无规则信号。"
    lines = [
        f"- 综合分: {rule_report.overall_score} ({rule_report.overall_fit_level})",
        f"- 能力匹配: {rule_report.capability_fit.level} ({rule_report.capability_fit.score})",
        f"- 经历相关: {rule_report.experience_relevance.level} ({rule_report.experience_relevance.score})",
        f"- 成长潜力: {rule_report.growth_potential.level} ({rule_report.growth_potential.score})",
        f"- 证据充分: {rule_report.evidence_strength.level} ({rule_report.evidence_strength.score})",
        f"- 风险短板: {rule_report.risks_and_gaps.level} ({rule_report.risks_and_gaps.score})",
    ]
    if rule_report.strengths:
        lines.append(f"- 规则识别优势: {', '.join(rule_report.strengths[:5])}")
    if rule_report.gaps:
        lines.append(f"- 规则识别差距: {', '.join(rule_report.gaps[:5])}")
    return "\n".join(lines)


def _strip_sensitive(profile: CandidateProfileResult) -> dict:
    """从候选人画像中移除敏感字段，只保留分析所需信息"""
    return {
        "education_background": profile.education_background,
        "skill_stack": profile.skill_stack,
        "projects": profile.projects,
        "internships": profile.internships,
        "work_experiences": profile.work_experiences,
        "business_understanding": profile.business_understanding,
        "achievements": profile.achievements,
        "learning_signals": profile.learning_signals,
        "transferable_strengths": profile.transferable_strengths,
        "collaboration_signals": profile.collaboration_signals,
        "risk_points": profile.risk_points,
        "confidence": profile.confidence,
        # sensitive_detected 不传给 LLM
    }


def _parse_agent_json(raw: str) -> Optional[dict]:
    """从 LLM 输出中提取 JSON，容忍 Markdown 包裹"""
    # 先试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 尝试从 ```json ... ``` 中提取
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试找到第一个 { 到最后一个 }
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _to_dimension(d: dict) -> DimensionResult:
    """将 LLM 输出的维度 dict 转为 DimensionResult"""
    if not isinstance(d, dict):
        return DimensionResult()
    return DimensionResult(
        level=d.get("level", "moderate"),
        score=float(d.get("score", 0)),
        summary=d.get("summary", ""),
        evidence_refs=d.get("evidence_refs", []),
    )


def _validate_and_convert(data: dict, rule_report: Optional[FitAnalysisResult]) -> Optional[FitAnalysisResult]:
    """校验 LLM 输出并转为 FitAnalysisResult，不合格返回 None"""
    try:
        result = FitAnalysisResult(
            overall_fit_level=data.get("overall_fit_level", "moderate"),
            overall_score=float(data.get("overall_score", 0)),
            fit_summary=data.get("fit_summary", ""),
            capability_fit=_to_dimension(data.get("capability_fit", {})),
            experience_relevance=_to_dimension(data.get("experience_relevance", {})),
            growth_potential=_to_dimension(data.get("growth_potential", {})),
            evidence_strength=_to_dimension(data.get("evidence_strength", {})),
            risks_and_gaps=_to_dimension(data.get("risks_and_gaps", {})),
            strengths=data.get("strengths", []),
            gaps=data.get("gaps", []),
            transferable_strengths=data.get("transferable_strengths", []),
            learning_plan=data.get("learning_plan", []),
            interview_strategy=data.get("interview_strategy", []),
            evidence_refs=data.get("evidence_refs", []),
            confidence=data.get("confidence", "low"),
        )
        # 基本校验
        if result.overall_fit_level not in ("strong", "moderate", "weak"):
            return None
        if not (0 <= result.overall_score <= 100):
            return None
        for dim in [result.capability_fit, result.experience_relevance,
                    result.growth_potential, result.evidence_strength, result.risks_and_gaps]:
            if dim.level not in ("strong", "moderate", "weak"):
                return None
        return result
    except Exception:
        return None


def analyze_fit_with_agent(
    job_profile: JobProfileResult,
    candidate_profile: CandidateProfileResult,
    rule_report: Optional[FitAnalysisResult] = None,
) -> tuple[FitAnalysisResult, str]:
    """
    LLM 综合适配分析，失败自动 fallback 到规则报告。

    Returns:
        (FitAnalysisResult, analysis_mode) — mode 为 "agent" 或 "rule_fallback"
    """
    # 1. 先确保有规则报告
    if rule_report is None:
        rule_report = analyze_fit(job_profile, candidate_profile)

    # 2. 构造 prompt
    safe_cand = _strip_sensitive(candidate_profile)
    prompt = AGENT_PROMPT.format(
        job_profile=json.dumps(job_profile.model_dump(), ensure_ascii=False, indent=2),
        candidate_profile=json.dumps(safe_cand, ensure_ascii=False, indent=2),
        rule_signals=_build_rule_signals(rule_report),
    )

    # 3. 调用 LLM
    try:
        llm = get_utility_llm()
        raw = llm.invoke(prompt).content.strip()
    except Exception as e:
        logger.warning(f"FitAnalysisAgent LLM 调用失败，fallback 规则: {e}")
        return rule_report, "rule_fallback"

    # 4. 解析 JSON
    data = _parse_agent_json(raw)
    if data is None:
        logger.warning(f"FitAnalysisAgent JSON 解析失败，fallback 规则。LLM输出前100字: {raw[:100]}")
        return rule_report, "rule_fallback"

    # 5. Schema 校验
    result = _validate_and_convert(data, rule_report)
    if result is None:
        logger.warning(f"FitAnalysisAgent schema 校验失败，fallback 规则。data keys: {list(data.keys())}")
        return rule_report, "rule_fallback"

    logger.info(f"FitAnalysisAgent 完成: {result.overall_fit_level} ({result.overall_score})")
    return result, "agent"
