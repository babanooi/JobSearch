"""v0.9 岗位画像、候选人画像、适配分析、反馈数据模型"""
import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, Integer, String, Text, Float, ForeignKey
from sqlalchemy.sql import func
from models.database import Base


class JobProfile(Base):
    """结构化岗位画像"""
    __tablename__ = "job_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_name: Mapped[str] = mapped_column(String(255), index=True, comment="岗位名")
    profile_version: Mapped[str] = mapped_column(String(20), default="1.0", comment="画像版本")
    source_document_ids: Mapped[str] = mapped_column(Text, default="[]", comment="来源 JD 文档 ID 列表 (JSON)")
    sample_count: Mapped[int] = mapped_column(Integer, default=0, comment="分析使用的 JD 样本数")
    job_type: Mapped[str] = mapped_column(String(50), default="", comment="岗位类型: 实习/校招/正式/未知")
    employment_type: Mapped[str] = mapped_column(String(50), default="", comment="用工类型: 全职/兼职/实习/合同")
    target_audience: Mapped[str] = mapped_column(String(100), default="", comment="面向人群")
    responsibilities: Mapped[str] = mapped_column(Text, default="[]", comment="核心职责 (JSON)")
    must_have_capabilities: Mapped[str] = mapped_column(Text, default="[]", comment="必备能力 (JSON)")
    nice_to_have_capabilities: Mapped[str] = mapped_column(Text, default="[]", comment="加分能力 (JSON)")
    experience_requirement: Mapped[str] = mapped_column(String(100), default="", comment="经验要求")
    education_preference: Mapped[str] = mapped_column(String(100), default="", comment="学历倾向")
    major_preference: Mapped[str] = mapped_column(String(200), default="", comment="专业倾向")
    business_context: Mapped[str] = mapped_column(Text, default="[]", comment="业务场景 (JSON)")
    growth_context: Mapped[str] = mapped_column(Text, default="[]", comment="成长空间 (JSON)")
    evidence: Mapped[str] = mapped_column(Text, default="[]", comment="证据片段 (JSON)")
    confidence: Mapped[str] = mapped_column(String(20), default="low", comment="整体置信度: high/medium/low")
    quality_flags: Mapped[str] = mapped_column(Text, default="[]", comment="质量标记 (JSON)")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class CandidateProfile(Base):
    """结构化候选人画像"""
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True, comment="关联用户")
    profile_version: Mapped[str] = mapped_column(String(20), default="1.0")
    source_type: Mapped[str] = mapped_column(String(30), default="resume_text", comment="来源类型: resume_text/file/conversation")
    resume_filename: Mapped[str] = mapped_column(String(200), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="", comment="原始简历文本")
    education_background: Mapped[str] = mapped_column(Text, default="{}", comment="教育背景 (JSON)")
    skill_stack: Mapped[str] = mapped_column(Text, default="[]", comment="技能栈 (JSON)")
    projects: Mapped[str] = mapped_column(Text, default="[]", comment="项目经历 (JSON)")
    internships: Mapped[str] = mapped_column(Text, default="[]", comment="实习经历 (JSON)")
    work_experiences: Mapped[str] = mapped_column(Text, default="[]", comment="工作经历 (JSON)")
    business_understanding: Mapped[str] = mapped_column(Text, default="[]", comment="业务理解 (JSON)")
    achievements: Mapped[str] = mapped_column(Text, default="[]", comment="成果证据 (JSON)")
    learning_signals: Mapped[str] = mapped_column(Text, default="[]", comment="学习能力信号 (JSON)")
    transferable_strengths: Mapped[str] = mapped_column(Text, default="[]", comment="可迁移优势 (JSON)")
    collaboration_signals: Mapped[str] = mapped_column(Text, default="[]", comment="协作信号 (JSON)")
    risk_points: Mapped[str] = mapped_column(Text, default="[]", comment="风险点 (JSON)")
    evidence: Mapped[str] = mapped_column(Text, default="[]", comment="证据片段 (JSON)")
    confidence: Mapped[str] = mapped_column(String(20), default="low")
    sensitive_detected: Mapped[str] = mapped_column(Text, default="[]", comment="检测到的敏感信息 (JSON)")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class FitAnalysisReport(Base):
    """岗位-候选人综合适配分析报告"""
    __tablename__ = "fit_analysis_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    job_profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("job_profiles.id"), index=True)
    candidate_profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("candidate_profiles.id"), index=True)
    report_version: Mapped[str] = mapped_column(String(20), default="1.0")
    overall_fit_level: Mapped[str] = mapped_column(String(20), default="moderate", comment="strong/moderate/weak")
    overall_score: Mapped[float] = mapped_column(Float, default=0.0, comment="综合适配分 0-100")
    fit_summary: Mapped[str] = mapped_column(Text, default="", comment="综合适配结论")
    capability_fit: Mapped[str] = mapped_column(Text, default="{}", comment="能力匹配度 (JSON)")
    experience_relevance: Mapped[str] = mapped_column(Text, default="{}", comment="经历相关性 (JSON)")
    growth_potential: Mapped[str] = mapped_column(Text, default="{}", comment="成长潜力 (JSON)")
    evidence_strength: Mapped[str] = mapped_column(Text, default="{}", comment="证据充分度 (JSON)")
    risks_and_gaps: Mapped[str] = mapped_column(Text, default="{}", comment="风险与短板 (JSON)")
    strengths: Mapped[str] = mapped_column(Text, default="[]", comment="优势 (JSON)")
    gaps: Mapped[str] = mapped_column(Text, default="[]", comment="差距 (JSON)")
    transferable_strengths: Mapped[str] = mapped_column(Text, default="[]", comment="可迁移优势 (JSON)")
    learning_plan: Mapped[str] = mapped_column(Text, default="[]", comment="学习计划 (JSON)")
    interview_strategy: Mapped[str] = mapped_column(Text, default="[]", comment="面试策略 (JSON)")
    evidence_refs: Mapped[str] = mapped_column(Text, default="[]", comment="证据引用 (JSON)")
    confidence: Mapped[str] = mapped_column(String(20), default="low")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class ProfileFeedback(Base):
    """通用画像反馈"""
    __tablename__ = "profile_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(50), index=True, comment="job_profile / candidate_profile / fit_analysis_report")
    target_id: Mapped[int] = mapped_column(Integer, index=True, comment="目标记录 ID")
    field_name: Mapped[str] = mapped_column(String(100), default="", comment="反馈针对的字段名")
    item_name: Mapped[str] = mapped_column(String(200), default="", comment="反馈针对的具体项目名")
    action: Mapped[str] = mapped_column(String(20), comment="reject/important/correct/wrong/missing/confirm")
    comment: Mapped[str] = mapped_column(Text, default="", comment="用户备注")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
