"""FastAPI 服务 —— REST API + 静态文件"""
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from models.database import init_database
from agents.registry import registry
from graphs.analyze import agent_graph as analyze_graph
from memory.long_term import (
    list_analyzed_jobs, list_user_conversations, get_or_create_user,
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
            return {"code": 200, "messages": msgs}
    except Exception:
        pass
    return {"code": 200, "messages": []}


# ── 历史对话 ──
@app.get("/conversations")
def get_conversations(user_id: int = Query(0)):
    if not user_id:
        return {"code": 200, "conversations": []}
    convs = list_user_conversations(user_id)
    return {"code": 200, "conversations": convs}


# ── 已分析岗位列表 ──
@app.get("/skill_rank/_jobs")
def get_analyzed_jobs():
    jobs = list_analyzed_jobs()
    return {"code": 200, "jobs": jobs}


# ── 技能排名 ──
@app.get("/skill_rank/{job_name}")
def get_skill_rank(job_name: str, top_n: int = 10):
    job_name = normalize_job_name(job_name)
    logger.info(f"GET /skill_rank/{job_name} top_n={top_n}")
    rank = db.get_skill_rank(job_name, top_n)
    # JD数量 + 更新时间：优先 jd_documents（精确），回退 job_skills.total_jds + last_seen_at
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
        # jd_documents 为空时回退到 job_skills 表
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
    last_update_str = last_update.strftime("%Y-%m-%d %H:%M") if last_update else ""
    return {"code": 200, "data": rank, "total_jds": jd_total, "last_update": last_update_str}


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
