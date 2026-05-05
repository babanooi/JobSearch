import time
import uuid
from pydantic import BaseModel
from graph.workflow import agent_graph
from agents.registry import registry
from fastapi import FastAPI
from database.db import init_database
from utils.logger import get_logger

db = registry.db_tool

logger = get_logger(__name__)

app = FastAPI(title="企业级多Agent岗位技能分析系统")


@app.on_event("startup")
def on_startup():
    logger.info("服务启动，初始化数据库...")
    init_database()
    logger.info("数据库初始化完成")


class JobRequest(BaseModel):
    job_name: str


@app.post("/analyze_job")
def analyze_job(request: JobRequest):
    """
    传入岗位名称 → 触发多Agent工作流
    流程：标准化 → 搜索 → 评估 → (回环) → 抽取 → 入库
    """
    t0 = time.time()
    thread_id = str(uuid.uuid4())
    logger.info(f"POST /analyze_job 收到请求: job_name={request.job_name}, thread_id={thread_id}")

    result = agent_graph.invoke(
        {"job_name": request.job_name, "status": "开始执行"},
        config={"configurable": {"thread_id": thread_id}},
    )

    elapsed = time.time() - t0
    logger.info(f"POST /analyze_job 完成 → 耗时 {elapsed:.1f}s, thread_id={thread_id}")

    return {
        "code": 200,
        "msg": "分析完成",
        "status": result["status"],
        "elapsed": f"{elapsed:.1f}s",
        "thread_id": thread_id,
    }


@app.get("/skill_rank/{job_name}")
def get_skill_rank(job_name: str, top_n: int = 10):
    """
    获取岗位最受关注的技能关键词top10
    """
    logger.info(f"GET /skill_rank/{job_name} top_n={top_n}")
    rank = db.get_skill_rank(job_name, top_n)
    logger.debug(f"GET /skill_rank/{job_name} 返回 {len(rank)} 条")
    return {"code": 200, "data": rank}
