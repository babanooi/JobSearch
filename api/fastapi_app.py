import time
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

from models.database import init_database
from agents.registry import registry
from graphs.analyze import agent_graph as analyze_graph
from core.logger import get_logger

logger = get_logger(__name__)
db = registry.db_tool

app = FastAPI(title="求职技能分析系统")


@app.on_event("startup")
def on_startup():
    logger.info("服务启动，初始化数据库...")
    init_database()
    logger.info("数据库初始化完成")


class JobRequest(BaseModel):
    job_name: str


@app.post("/analyze_job")
def analyze_job(request: JobRequest):
    t0 = time.time()
    thread_id = str(uuid.uuid4())
    logger.info(f"POST /analyze_job job_name={request.job_name} thread_id={thread_id}")

    result = analyze_graph.invoke(
        {"job_name": request.job_name, "status": "开始执行"},
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


@app.get("/skill_rank/{job_name}")
def get_skill_rank(job_name: str, top_n: int = 10):
    logger.info(f"GET /skill_rank/{job_name} top_n={top_n}")
    rank = db.get_skill_rank(job_name, top_n)
    return {"code": 200, "data": rank}


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


@app.post("/chat")
def chat(request: ChatRequest):
    from graphs.chat import chat_agent_graph, new_thread_id

    tid = request.thread_id or new_thread_id()
    result = chat_agent_graph.invoke(
        {"thread_id": tid, "messages": [], "user_input": request.message,
         "summary": "", "knowledge": [], "response": ""},
        config={"configurable": {"thread_id": tid}},
    )
    return {"code": 200, "response": result.get("response", ""), "thread_id": tid}
