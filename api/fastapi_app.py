"""FastAPI 服务 —— REST API + 静态文件"""
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from models.database import init_database
from agents.registry import registry
from graphs.analyze import agent_graph as analyze_graph
from memory.long_term import (
    list_analyzed_jobs, list_user_conversations, get_or_create_user,
    delete_user_data, delete_conversation_data,
)
from tools.skill_guard import normalize_job_name
from core.task_manager import task_manager
from core.logger import get_logger

logger = get_logger(__name__)
db = registry.db_tool

STATIC_DIR = Path(__file__).resolve().parent.parent / "ui" / "static"

app = FastAPI(title="求职技能分析助手")


@app.on_event("startup")
def on_startup():
    logger.info("服务启动，初始化数据库...")
    init_database()
    logger.info("数据库初始化完成")


# ── 静态文件 ──
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ── 用户 ──
@app.get("/users")
def list_users():
    """列出所有用户"""
    from models.database import SessionLocal
    from models.user import User
    with SessionLocal() as session:
        rows = session.query(User).order_by(User.id).all()
    return {"code": 200, "users": [{"id": r.id, "username": r.username} for r in rows]}


@app.get("/user")
def create_or_get_user(username: str = Query("")):
    name = username or f"用户_{str(uuid.uuid4())[:8]}"
    uid = get_or_create_user(name)
    return {"code": 200, "user_id": uid, "username": name}


@app.delete("/user/{user_id}")
def delete_user(user_id: int):
    result = delete_user_data(user_id)
    return {"code": 200, **result}


# ── 对话 ──
class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    user_id: int | None = None


@app.post("/chat")
def chat(request: ChatRequest):
    from graphs.chat import chat_agent_graph, new_thread_id

    tid = request.thread_id or new_thread_id()
    uid = request.user_id or 0

    if uid and not request.thread_id:
        get_or_create_user(f"用户_{tid[:8]}")

    task = task_manager.create("chat")

    def _run(task, _tid, _uid, _msg):
        task.progress = "分析意图..."
        result = chat_agent_graph.invoke(
            {"thread_id": _tid, "user_id": _uid, "user_input": _msg, "task": task},
            config={"configurable": {"thread_id": _tid}},
        )
        return {
            "code": 200,
            "response": result.get("response", ""),
            "thread_id": _tid,
            "knowledge": result.get("knowledge", []),
        }

    task_manager.run(task, _run, tid, uid, request.message)
    return {"code": 200, "task_id": task.task_id, "thread_id": tid, "async": True}


# ── 任务状态查询 ──
@app.get("/task/{task_id}")
def get_task(task_id: str):
    task = task_manager.get(task_id)
    if not task:
        return {"code": 404, "message": "任务不存在"}
    return {"code": 200, "task": task.to_dict()}


@app.post("/task/{task_id}/cancel")
def cancel_task(task_id: str):
    ok = task_manager.cancel(task_id)
    return {"code": 200, "cancelled": ok}


# ── 技能差距分析 ──
class SkillGapRequest(BaseModel):
    job_name: str
    user_skills: list[str] = Field(default_factory=list)
    user_profile: list[dict] = Field(default_factory=list)
    top_n: int = Field(default=15, ge=1, le=50)


@app.post("/skill_gap")
def skill_gap(request: SkillGapRequest):
    if not request.job_name or not request.job_name.strip():
        raise HTTPException(status_code=400, detail="job_name 不能为空")
    from services.skill_gap import analyze_skill_gap
    from services.resume_profile import profile_to_skill_names
    profile_skills = profile_to_skill_names(request.user_profile)
    user_skills = list(dict.fromkeys([*profile_skills, *request.user_skills]))
    result = analyze_skill_gap(
        job_name=request.job_name,
        user_skills=user_skills,
        top_n=request.top_n,
    )
    result["profile_skills"] = profile_skills
    return {"code": 200, **result}


# ── 简历画像分析 ──
class ResumeTextRequest(BaseModel):
    resume_text: str = Field(default="")


@app.post("/profile/resume_text")
def profile_resume_text(request: ResumeTextRequest):
    from services.resume_profile import extract_profile_from_text
    profile = extract_profile_from_text(request.resume_text)
    return {"code": 200, "profile": profile}


@app.post("/profile/resume")
async def profile_resume(
    resume_text: str = Form(default=""),
    file: UploadFile | None = File(default=None),
):
    from services.resume_profile import extract_profile_from_text, extract_text_from_file
    text = resume_text or ""
    filename = ""
    if file is not None:
        filename = file.filename or ""
        text = extract_text_from_file(file.file, filename=filename)
    if not text.strip():
        raise HTTPException(status_code=400, detail="未能从简历中提取文本，请粘贴文本版简历或上传可复制文本的 PDF/DOCX/TXT。")
    profile = extract_profile_from_text(text)
    return {"code": 200, "filename": filename, "text_length": len(text), "profile": profile}


# ── v0.7 岗位画像 / 候选人画像 / 初筛模拟 ──
class CandidateProfileRequest(BaseModel):
    resume_text: str = Field(default="")
    user_profile: list[dict] = Field(default_factory=list)


class ScreeningReportRequest(BaseModel):
    job_name: str
    resume_text: str = Field(default="")
    user_profile: list[dict] = Field(default_factory=list)
    top_n: int = Field(default=20, ge=1, le=50)


@app.get("/job_profile/{job_name}")
def job_profile(job_name: str, top_n: int = Query(20, ge=1, le=50)):
    if not job_name or not job_name.strip():
        raise HTTPException(status_code=400, detail="job_name 不能为空")
    from services.screening import build_job_profile
    return {"code": 200, "profile": build_job_profile(job_name, top_n=top_n)}


@app.post("/candidate_profile")
def candidate_profile(request: CandidateProfileRequest):
    from services.screening import extract_candidate_profile
    profile = extract_candidate_profile(
        resume_text=request.resume_text,
        user_profile=request.user_profile,
    )
    return {"code": 200, "profile": profile}


@app.post("/screening_report")
def screening_report(request: ScreeningReportRequest):
    if not request.job_name or not request.job_name.strip():
        raise HTTPException(status_code=400, detail="job_name 不能为空")
    from services.screening import build_screening_report
    report = build_screening_report(
        job_name=request.job_name,
        resume_text=request.resume_text,
        user_profile=request.user_profile,
        top_n=request.top_n,
    )
    return {"code": 200, "report": report}


# ── 深度研究（直接走 research_graph，不经过 ChatAgent） ──
class ResearchRequest(BaseModel):
    topic: str


@app.post("/research")
def research(request: ResearchRequest):
    """直接从已有数据库搜索多维度信息，LLM 生成研究报告"""
    from graphs.research import research_graph
    import uuid

    tid = str(uuid.uuid4())
    logger.info(f"POST /research topic={request.topic[:50]}...")

    t0 = time.time()
    result = research_graph.invoke(
        {"user_input": request.topic, "messages": []},
        config={"configurable": {"thread_id": f"research_{tid}"}},
    )
    elapsed = time.time() - t0
    logger.info(f"POST /research 完成 -> 耗时 {elapsed:.1f}s, {len(result.get('knowledge',[]))} 卡片")

    return {
        "code": 200,
        "knowledge": result.get("knowledge", []),
        "response": result.get("response", ""),
        "elapsed": f"{elapsed:.1f}s",
    }


# ── 对话历史消息 ──
@app.get("/conversation/{thread_id}")
def get_conversation_messages(thread_id: str):
    """从 SqliteSaver 恢复对话消息"""
    from graphs.chat import chat_agent_graph
    try:
        state = chat_agent_graph.get_state(
            config={"configurable": {"thread_id": thread_id}}
        )
        if state and state.values:
            msgs = state.values.get("messages", [])
            if msgs:
                return {"code": 200, "messages": msgs}
    except Exception as e:
        logger.warning(f"graph state 恢复会话失败: {thread_id[:8]}... {e}")
    try:
        from memory.short_term import load_messages_from_writes
        msgs = load_messages_from_writes(thread_id)
        if msgs:
            return {"code": 200, "messages": msgs, "source": "writes"}
    except Exception as e:
        logger.warning(f"writes fallback 恢复会话失败: {thread_id[:8]}... {e}")
    return {"code": 200, "messages": []}


@app.delete("/conversation/{thread_id}")
def delete_conversation(thread_id: str, user_id: int = Query(0)):
    result = delete_conversation_data(thread_id, user_id or None)
    return {"code": 200, **result}


# ── 历史对话 ──
@app.get("/conversations")
def get_conversations(user_id: int = Query(0), include_orphans: bool = Query(True)):
    if not user_id:
        return {"code": 200, "conversations": []}
    convs = list_user_conversations(user_id)
    if include_orphans:
        try:
            from memory.short_term import list_checkpoint_threads
            known = {c["thread_id"] for c in convs}
            for item in list_checkpoint_threads():
                tid = item["thread_id"]
                if tid in known:
                    continue
                convs.append({
                    "thread_id": tid,
                    "title": f"恢复会话 {tid[:8]}",
                    "created_at": "",
                    "updated_at": "",
                    "recovered": True,
                })
        except Exception as e:
            logger.warning(f"恢复 checkpoint 会话列表失败: {e}")
    return {"code": 200, "conversations": convs}


# ── 技能反馈 ──
class SkillFeedbackRequest(BaseModel):
    user_id: int
    job_name: str
    skill_name: str
    action: str = Field(pattern="^(reject|important)$")


@app.post("/skill_feedback")
def post_skill_feedback(request: SkillFeedbackRequest):
    from models.user import SkillFeedback
    from models.database import SessionLocal as _SessionLocal
    job_name = normalize_job_name(request.job_name)
    with _SessionLocal() as session:
        existing = session.query(SkillFeedback).filter(
            SkillFeedback.user_id == request.user_id,
            SkillFeedback.job_name == job_name,
            SkillFeedback.skill_name == request.skill_name,
            SkillFeedback.action == request.action,
        ).first()
        if not existing:
            session.add(SkillFeedback(
                user_id=request.user_id,
                job_name=job_name,
                skill_name=request.skill_name,
                action=request.action,
            ))
            session.commit()
    return {"code": 200, "message": "ok"}


@app.get("/skill_feedback/summary")
def get_skill_feedback_summary(job_name: str, user_id: int = Query(0)):
    from models.user import SkillFeedback
    from models.database import SessionLocal as _SessionLocal
    from sqlalchemy import func as sqlfunc
    job_name = normalize_job_name(job_name)
    with _SessionLocal() as session:
        rows = session.query(
            SkillFeedback.skill_name,
            SkillFeedback.action,
            sqlfunc.count().label("cnt"),
        ).filter(
            SkillFeedback.job_name == job_name,
        ).group_by(SkillFeedback.skill_name, SkillFeedback.action).all()

        # 当前用户的反馈
        user_rows = set()
        if user_id:
            urows = session.query(SkillFeedback.skill_name, SkillFeedback.action).filter(
                SkillFeedback.job_name == job_name,
                SkillFeedback.user_id == user_id,
            ).all()
            user_rows = {(r[0], r[1]) for r in urows}

    summary = {}
    for skill, action, cnt in rows:
        if skill not in summary:
            summary[skill] = {"reject_count": 0, "important_count": 0, "user_rejected": False, "user_marked_important": False}
        summary[skill][f"{action}_count"] = cnt
        if (skill, "reject") in user_rows:
            summary[skill]["user_rejected"] = True
        if (skill, "important") in user_rows:
            summary[skill]["user_marked_important"] = True

    return {"code": 200, "job_name": job_name, "summary": summary}


# ── 已分析岗位列表 ──
@app.get("/skill_rank/_jobs")
def get_analyzed_jobs():
    jobs = list_analyzed_jobs()
    return {"code": 200, "jobs": jobs}


# ── 技能排名 ──
@app.get("/skill_rank/{job_name}")
def get_skill_rank(job_name: str, top_n: int = 10, user_id: int = Query(0)):
    from services.skill_gap import filter_market_skills, estimate_market_confidence
    from models.user import SkillFeedback
    from sqlalchemy import func as sqlfunc
    job_name = normalize_job_name(job_name)
    logger.info(f"GET /skill_rank/{job_name} top_n={top_n}")

    # 多取一些原始数据，过滤后再截取
    raw_rank = db.get_skill_rank(job_name, min(top_n * 2, 50))

    # 过滤低质量泛词，每项带 confidence + quality_reasons
    rank = filter_market_skills(raw_rank, job_name=job_name, top_n=top_n)

    # JD数量 + 更新时间
    from models.database import SessionLocal
    from sqlalchemy import text
    with SessionLocal() as session:
        jd_total = session.execute(
            text("SELECT COUNT(*) FROM jd_documents WHERE job_name = :job"),
            {"job": job_name},
        ).scalar() or 0
        last_update = session.execute(
            text("SELECT MAX(fetched_at) FROM jd_documents WHERE job_name = :job"),
            {"job": job_name},
        ).scalar()
        if not jd_total:
            jd_total = session.execute(
                text("SELECT COALESCE(MAX(total_jds), 0) FROM job_skills WHERE job_name = :job"),
                {"job": job_name},
            ).scalar() or 0
        if not last_update:
            last_update = session.execute(
                text("SELECT MAX(last_seen_at) FROM job_skills WHERE job_name = :job"),
                {"job": job_name},
            ).scalar()

        # 反馈汇总
        fb_rows = session.query(
            SkillFeedback.skill_name,
            SkillFeedback.action,
            sqlfunc.count().label("cnt"),
        ).filter(
            SkillFeedback.job_name == job_name,
        ).group_by(SkillFeedback.skill_name, SkillFeedback.action).all()

        user_fb = set()
        if user_id:
            urows = session.query(SkillFeedback.skill_name, SkillFeedback.action).filter(
                SkillFeedback.job_name == job_name,
                SkillFeedback.user_id == user_id,
            ).all()
            user_fb = {(r[0], r[1]) for r in urows}

    fb_map = {}
    for skill, action, cnt in fb_rows:
        if skill not in fb_map:
            fb_map[skill] = {"reject_count": 0, "important_count": 0}
        fb_map[skill][f"{action}_count"] = cnt

    # 给每个技能附加反馈标记
    for item in rank:
        s = item["skill"]
        fb = fb_map.get(s, {})
        item["reject_count"] = fb.get("reject_count", 0)
        item["important_count"] = fb.get("important_count", 0)
        item["user_rejected"] = (s, "reject") in user_fb
        item["user_marked_important"] = (s, "important") in user_fb
        item["community_rejected"] = item["reject_count"] >= 3
        item["community_important"] = item["important_count"] >= 3

    last_update_str = last_update.strftime("%Y-%m-%d %H:%M") if last_update else ""
    conf = estimate_market_confidence(rank, raw_count=len(raw_rank), total_jds=jd_total or 0)

    return {
        "code": 200,
        "data": rank,
        "total_jds": jd_total,
        "last_update": last_update_str,
        "confidence": conf["confidence"],
        "filtered_count": conf["filtered_count"],
    }


# ── 简历文件解析 ──
@app.post("/resume/parse")
async def parse_resume(file: UploadFile = File(default=None)):
    if not file:
        raise HTTPException(status_code=400, detail="未上传文件")
    content = await file.read()
    try:
        from services.resume_parser import parse_resume_file
        result = parse_resume_file(
            filename=file.filename or "",
            content=content,
            content_type=file.content_type or "",
        )
        return {"code": 200, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"简历解析异常: {e}")
        raise HTTPException(status_code=500, detail="简历解析失败，请手动粘贴简历文本")


# ═══ v0.9 画像 + 适配分析 API ═══

# ── 岗位画像 ──
class JobProfileRequest(BaseModel):
    job_name: str
    top_n: int = Field(default=20, ge=1, le=50)


@app.post("/job_profiles/analyze")
def analyze_job_profile(request: JobProfileRequest):
    from services.job_profile_service import extract_job_profile, save_job_profile
    profile = extract_job_profile(request.job_name, top_n=request.top_n)
    profile_id = save_job_profile(profile)
    return {"code": 200, "job_profile_id": profile_id, "profile": profile.model_dump()}


@app.get("/job_profiles/{profile_id}")
def get_job_profile(profile_id: int):
    from models.profile import JobProfile
    from models.database import SessionLocal as _SL
    with _SL() as session:
        obj = session.get(JobProfile, profile_id)
        if not obj:
            return {"code": 404, "message": "岗位画像不存在"}
        return {"code": 200, "profile": {k: getattr(obj, k) for k in [
            "id", "job_name", "job_type", "employment_type", "target_audience",
            "responsibilities", "must_have_capabilities", "nice_to_have_capabilities",
            "experience_requirement", "education_preference", "major_preference",
            "business_context", "growth_context", "evidence", "confidence",
            "quality_flags", "sample_count", "created_at",
        ]}}


# ── 候选人画像 ──
class CandidateProfileRequest(BaseModel):
    user_id: int
    resume_text: str = ""
    resume_filename: str = ""
    conversation_text: str = ""


@app.post("/candidate_profiles/analyze")
def analyze_candidate_profile(request: CandidateProfileRequest):
    from services.candidate_profile_service import extract_candidate_profile, save_candidate_profile
    profile = extract_candidate_profile(
        resume_text=request.resume_text,
        user_id=request.user_id,
        resume_filename=request.resume_filename,
        conversation_text=request.conversation_text,
    )
    profile_id = save_candidate_profile(profile, user_id=request.user_id, resume_filename=request.resume_filename)
    return {"code": 200, "candidate_profile_id": profile_id, "profile": profile.model_dump()}


@app.get("/candidate_profiles/{profile_id}")
def get_candidate_profile(profile_id: int):
    from models.profile import CandidateProfile
    from models.database import SessionLocal as _SL
    with _SL() as session:
        obj = session.get(CandidateProfile, profile_id)
        if not obj:
            return {"code": 404, "message": "候选人画像不存在"}
        return {"code": 200, "profile": {k: getattr(obj, k) for k in [
            "id", "user_id", "education_background", "skill_stack",
            "projects", "internships", "work_experiences",
            "business_understanding", "achievements", "learning_signals",
            "transferable_strengths", "collaboration_signals", "risk_points",
            "evidence", "confidence", "sensitive_detected", "created_at",
        ]}}


# ── 综合适配分析 ──
class FitAnalysisRequest(BaseModel):
    user_id: int
    job_profile_id: int
    candidate_profile_id: int


@app.post("/fit_analysis_reports")
def create_fit_analysis(request: FitAnalysisRequest):
    from models.profile import JobProfile, CandidateProfile
    from models.database import SessionLocal as _SL
    from services.fit_analysis_service import analyze_fit, save_fit_analysis
    from services.fit_analysis_agent import analyze_fit_with_agent
    from services.profile_schemas import JobProfileResult, CandidateProfileResult

    with _SL() as session:
        jp = session.get(JobProfile, request.job_profile_id)
        cp = session.get(CandidateProfile, request.candidate_profile_id)
        if not jp or not cp:
            return {"code": 404, "message": "画像不存在"}

        import json
        job_result = JobProfileResult(
            job_name=jp.job_name,
            job_type=jp.job_type,
            employment_type=jp.employment_type,
            target_audience=jp.target_audience,
            responsibilities=json.loads(jp.responsibilities) if jp.responsibilities else [],
            must_have_capabilities=json.loads(jp.must_have_capabilities) if jp.must_have_capabilities else [],
            nice_to_have_capabilities=json.loads(jp.nice_to_have_capabilities) if jp.nice_to_have_capabilities else [],
            experience_requirement=jp.experience_requirement or "",
            education_preference=jp.education_preference or "",
            major_preference=jp.major_preference or "",
            business_context=json.loads(jp.business_context) if jp.business_context else [],
            growth_context=json.loads(jp.growth_context) if jp.growth_context else [],
            confidence=jp.confidence or "low",
            sample_count=jp.sample_count,
        )
        cand_result = CandidateProfileResult(
            education_background=json.loads(cp.education_background) if cp.education_background else {},
            skill_stack=json.loads(cp.skill_stack) if cp.skill_stack else [],
            projects=json.loads(cp.projects) if cp.projects else [],
            internships=json.loads(cp.internships) if cp.internships else [],
            work_experiences=json.loads(cp.work_experiences) if cp.work_experiences else [],
            business_understanding=json.loads(cp.business_understanding) if cp.business_understanding else [],
            achievements=json.loads(cp.achievements) if cp.achievements else [],
            learning_signals=json.loads(cp.learning_signals) if cp.learning_signals else [],
            transferable_strengths=json.loads(cp.transferable_strengths) if cp.transferable_strengths else [],
            collaboration_signals=json.loads(cp.collaboration_signals) if cp.collaboration_signals else [],
            risk_points=json.loads(cp.risk_points) if cp.risk_points else [],
            confidence=cp.confidence or "low",
            sensitive_detected=json.loads(cp.sensitive_detected) if cp.sensitive_detected else [],
        )

    # 先规则分析，再尝试 Agent
    rule_report = analyze_fit(job_result, cand_result)
    report, analysis_mode = analyze_fit_with_agent(job_result, cand_result, rule_report)

    report_id = save_fit_analysis(report, user_id=request.user_id,
                                  job_profile_id=request.job_profile_id,
                                  candidate_profile_id=request.candidate_profile_id)
    return {
        "code": 200,
        "fit_analysis_id": report_id,
        "report": report.model_dump(),
        "analysis_mode": analysis_mode,
        "rule_score": rule_report.overall_score,
    }


@app.get("/fit_analysis_reports/{report_id}")
def get_fit_analysis(report_id: int):
    from models.profile import FitAnalysisReport
    from models.database import SessionLocal as _SL
    with _SL() as session:
        obj = session.get(FitAnalysisReport, report_id)
        if not obj:
            return {"code": 404, "message": "适配分析报告不存在"}
        return {"code": 200, "report": {k: getattr(obj, k) for k in [
            "id", "user_id", "job_profile_id", "candidate_profile_id",
            "overall_fit_level", "overall_score", "fit_summary",
            "capability_fit", "experience_relevance", "growth_potential",
            "evidence_strength", "risks_and_gaps", "strengths", "gaps",
            "transferable_strengths", "learning_plan", "interview_strategy",
            "evidence_refs", "confidence", "created_at",
        ]}}


# ── 通用画像反馈 ──
class ProfileFeedbackRequest(BaseModel):
    user_id: int
    target_type: str = Field(pattern="^(job_profile|candidate_profile|fit_analysis_report)$")
    target_id: int
    field_name: str = ""
    item_name: str = ""
    action: str = Field(pattern="^(reject|important|correct|wrong|missing|confirm)$")
    comment: str = ""


@app.post("/profile_feedback")
def post_profile_feedback(request: ProfileFeedbackRequest):
    from models.profile import ProfileFeedback
    from models.database import SessionLocal as _SL
    with _SL() as session:
        session.add(ProfileFeedback(
            user_id=request.user_id,
            target_type=request.target_type,
            target_id=request.target_id,
            field_name=request.field_name,
            item_name=request.item_name,
            action=request.action,
            comment=request.comment,
        ))
        session.commit()
    return {"code": 200, "message": "ok"}


# ── 人工评估 ──
class ProfileEvaluationRequest(BaseModel):
    user_id: int
    target_type: str = Field(pattern="^(job_profile|candidate_profile|fit_analysis_report)$")
    target_id: int
    rating: int = Field(default=0, ge=0, le=5)
    is_correct: bool = True
    error_type: str = Field(default="", pattern="^(|missing_info|wrong_info|hallucination|weak_evidence|bad_suggestion|unfair_judgment|other)$")
    field_name: str = ""
    comment: str = ""
    useful_for_training: bool = False


@app.post("/profile_evaluations")
def post_evaluation(request: ProfileEvaluationRequest):
    from services.profile_evaluation_service import create_evaluation
    try:
        eval_id = create_evaluation(
            user_id=request.user_id,
            target_type=request.target_type,
            target_id=request.target_id,
            rating=request.rating,
            is_correct=request.is_correct,
            error_type=request.error_type,
            field_name=request.field_name,
            comment=request.comment,
            useful_for_training=request.useful_for_training,
        )
        return {"code": 200, "evaluation_id": eval_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/profile_evaluations")
def list_evaluations(
    target_type: str = Query(""),
    target_id: int = Query(0),
    user_id: int = Query(0),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    from services.profile_evaluation_service import list_evaluations
    items = list_evaluations(
        target_type=target_type,
        target_id=target_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return {"code": 200, "items": items}


@app.get("/profile_evaluations/summary")
def get_evaluation_summary(
    target_type: str = Query(""),
    user_id: int = Query(0),
):
    from services.profile_evaluation_service import summarize_evaluations
    summary = summarize_evaluations(target_type=target_type, user_id=user_id)
    return {"code": 200, **summary}


# ── 统计 ──
@app.get("/stats")
def get_stats():
    """返回技能库总数和JD总量"""
    from models.database import SessionLocal
    from sqlalchemy import text
    with SessionLocal() as session:
        skill_count = session.execute(text("SELECT COUNT(DISTINCT skill_name) FROM job_skills")).scalar() or 0
        jd_count = session.execute(text("SELECT COUNT(*) FROM jd_documents")).scalar() or 0
    return {"code": 200, "skill_count": skill_count, "jd_count": jd_count}


# ── 岗位分析（保留 API） ──
class JobRequest(BaseModel):
    job_name: str


@app.post("/analyze_job")
def analyze_job(request: JobRequest):
    t0 = time.time()
    thread_id = str(uuid.uuid4())
    job_name = normalize_job_name(request.job_name)
    logger.info(f"POST /analyze_job job_name={job_name} thread_id={thread_id}")

    result = analyze_graph.invoke(
        {"job_name": job_name, "status": "开始执行"},
        config={"configurable": {"thread_id": thread_id}},
    )

    elapsed = time.time() - t0
    logger.info(f"POST /analyze_job 完成 -> 耗时 {elapsed:.1f}s")

    return {
        "code": 200,
        "msg": "分析完成",
        "status": result["status"],
        "elapsed": f"{elapsed:.1f}s",
        "thread_id": thread_id,
    }
