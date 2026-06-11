"""Pydantic schemas for profile validation — v0.9"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class EvidenceItem(BaseModel):
    text: str = ""
    source: str = ""


class JobProfileResult(BaseModel):
    job_name: str
    job_type: str = "unknown"
    employment_type: str = "未知"
    target_audience: str = "未明确"
    responsibilities: list[str] = Field(default_factory=list)
    must_have_capabilities: list[str] = Field(default_factory=list)
    nice_to_have_capabilities: list[str] = Field(default_factory=list)
    experience_requirement: str = ""
    education_preference: str = ""
    major_preference: str = ""
    business_context: list[str] = Field(default_factory=list)
    growth_context: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: str = "low"
    quality_flags: list[str] = Field(default_factory=list)
    sample_count: int = 0
    valid_sample_count: int = 0
    filtered_sample_count: int = 0


class CandidateProfileResult(BaseModel):
    education_background: dict = Field(default_factory=dict)
    skill_stack: list[dict] = Field(default_factory=list)
    projects: list[dict] = Field(default_factory=list)
    internships: list[dict] = Field(default_factory=list)
    work_experiences: list[dict] = Field(default_factory=list)
    business_understanding: list[str] = Field(default_factory=list)
    achievements: list[dict] = Field(default_factory=list)
    learning_signals: list[str] = Field(default_factory=list)
    transferable_strengths: list[str] = Field(default_factory=list)
    collaboration_signals: list[str] = Field(default_factory=list)
    risk_points: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: str = "low"
    sensitive_detected: list[str] = Field(default_factory=list)
    summary: str = ""


class DimensionResult(BaseModel):
    level: str = "moderate"  # strong / moderate / weak
    score: float = 0.0
    summary: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class FitAnalysisResult(BaseModel):
    overall_fit_level: str = "moderate"
    overall_score: float = 0.0
    fit_summary: str = ""
    capability_fit: DimensionResult = Field(default_factory=DimensionResult)
    experience_relevance: DimensionResult = Field(default_factory=DimensionResult)
    growth_potential: DimensionResult = Field(default_factory=DimensionResult)
    evidence_strength: DimensionResult = Field(default_factory=DimensionResult)
    risks_and_gaps: DimensionResult = Field(default_factory=DimensionResult)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    transferable_strengths: list[str] = Field(default_factory=list)
    learning_plan: list[str] = Field(default_factory=list)
    interview_strategy: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: str = "low"
