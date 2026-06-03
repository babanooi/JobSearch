"""岗位技能分析工作流 —— search → store_jd → evaluate → extract → save"""
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from langgraph.graph import StateGraph, END
from langchain_core.prompts import PromptTemplate

from agents.registry import registry
from agents.base import get_utility_llm
from graphs.state import AgentState
from memory.short_term import create_checkpointer
from memory.long_term import clear_bm25_cache
from tools.skill_guard import normalize_job_name, normalize_skill_list, clear_skill_cache, guard_skill_list
from core.task_manager import TaskCancelledError
from core.logger import get_logger
from core.tracer import trace

search_agent = registry.search_agent
extract_agent = registry.extract_agent
db = registry.db_tool

logger = get_logger(__name__)

MAX_SEARCH_ROUNDS = 5


def search_node(state: AgentState) -> AgentState:
    raw_query = state.get("search_query", "")
    if raw_query.startswith("SEARCH|"):
        query = raw_query.split("|", 1)[1].strip()
    else:
        query = raw_query or state["job_name"]

    round_num = state.get("search_round", 0) + 1
    logger.info(f">>> search_node 第{round_num}轮搜索: {query}")

    with trace("search", f"Tavily 搜索 第{round_num}轮", model="tavily") as t:
        items = search_agent.run(query)
        t["round"] = round_num
        t["results"] = len(items)

    collected = list(state.get("search_raw_items") or [])
    collected.extend(items)

    logger.info(f"<<< search_node 第{round_num}轮完成，本轮 {len(items)} 条，累计 {len(collected)} 条")
    return {
        "search_raw_items": collected,
        "search_round": round_num,
        "search_query": raw_query,
        "status": "搜索完成",
    }


def evaluate_node(state: AgentState) -> AgentState:
    round_num = state.get("search_round", 0)
    logger.info(f">>> evaluate_node 第{round_num}轮评估中...")

    prompt = PromptTemplate.from_template("""
    你是招聘数据分析专家。判断当前搜索结果是否足够提取"{job_name}"岗位的技能。
    已收集{round_num}轮，上限{max_rounds}轮。
    已收集的招聘信息:
    {collected}
    信息足够则输出 FINISH，需要补搜则输出: SEARCH|<补搜关键词>
    只输出 FINISH 或 SEARCH|<关键词>，不要其他内容。
    """)

    llm = get_utility_llm()
    chain = prompt | llm
    items = state.get("search_raw_items", []) or []
    with trace("evaluate", f"LLM 评估 第{round_num}轮", model=llm.model_name) as t:
        msg = chain.invoke({
            "job_name": state["job_name"],
            "round_num": round_num,
            "max_rounds": MAX_SEARCH_ROUNDS,
            "collected": "\n---\n".join(item["content"] for item in items[-6:]),
        })
        decision = msg.content.strip()
        usage = msg.response_metadata.get("token_usage", {})
        t["round"] = round_num
        t["decision"] = decision
        t["tokens_prompt"] = usage.get("prompt_tokens", 0)
        t["tokens_completion"] = usage.get("completion_tokens", 0)

    logger.info(f"<<< evaluate_node 决策: {decision}")
    return {"status": f"评估结果: {decision}", "search_query": decision}


def route_after_evaluate(state: AgentState) -> str:
    decision = state.get("search_query", "")
    if state.get("search_round", 0) >= MAX_SEARCH_ROUNDS:
        logger.info("路由: 已达最大轮次 -> extract_node")
        return "extract_node"
    if decision.startswith("FINISH"):
        logger.info("路由: 评估充分 -> extract_node")
        return "extract_node"
    if decision.startswith("SEARCH|"):
        logger.info("路由: 需要补搜 -> search_node")
        return "search_node"
    logger.warning("路由: 无法解析决策，兜底 -> extract_node")
    return "extract_node"


def extract_node(state: AgentState) -> AgentState:
    items = state.get("search_raw_items", []) or []
    logger.info(f">>> extract_node 开始提取技能，共 {len(items)} 条 JD")
    t0 = time.time()

    # 分批：每 4 条 JD 一组，并行提取
    BATCH_SIZE = 4
    batches = [items[i:i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]

    all_skills = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    # 取消检查：开始提取前
    task = state.get("task")
    if task and task.is_cancelled():
        raise TaskCancelledError(f"任务 {task.task_id} 已取消")

    with trace("extract", f"LLM 提取 {len(items)}条JD ({len(batches)}批并行)", model=extract_agent.llm.model_name) as t:
        with ThreadPoolExecutor(max_workers=min(len(batches), 4)) as pool:
            futures = []
            for batch in batches:
                # 每批提交前检查取消，避免取消后还提交 v4-pro 调用
                if task and task.is_cancelled():
                    raise TaskCancelledError(f"任务 {task.task_id} 已取消")
                combined = "\n\n---\n\n".join(
                    item["content"][:300] for item in batch
                )
                futures.append(pool.submit(extract_agent.run, combined))

            for f in as_completed(futures):
                if task and task.is_cancelled():
                    raise TaskCancelledError(f"任务 {task.task_id} 已取消")
                skills, token_usage = f.result()
                all_skills.extend(skills)
                total_prompt_tokens += token_usage["prompt_tokens"]
                total_completion_tokens += token_usage["completion_tokens"]

        t["jd_count"] = len(items)
        t["batches"] = len(batches)
        t["skills_count"] = len(all_skills)
        t["tokens_prompt"] = total_prompt_tokens
        t["tokens_completion"] = total_completion_tokens
        t["parallel_speedup"] = f"{(time.time() - t0)*1000:.0f}ms total"

    logger.info(f"<<< extract_node 完成 -> 提取到 {len(all_skills)} 个技能（{len(batches)} 批并行）")
    return {"skill_list": all_skills}


def skill_reflect_node(state: AgentState) -> AgentState:
    """反思过滤：DB交叉对照 + LLM 审视"""
    raw_skills = state.get("skill_list", [])
    if not raw_skills:
        return {"skill_list": []}

    unique = list(set(raw_skills))
    from agents.base import get_utility_llm
    from sqlalchemy import text
    from models.database import SessionLocal

    # 从 MySQL 拉取已有技能库作为参考白名单
    existing_skills = set()
    try:
        with SessionLocal() as session:
            rows = session.execute(text("SELECT DISTINCT skill_name FROM job_skills")).fetchall()
            existing_skills = {r[0].lower() for r in rows}
    except Exception as e:
        logger.warning(f"拉取已有技能库失败: {e}")

    # 分类：已知技能直接保留，未知的交给 LLM 判断
    auto_keep = []
    need_review = []
    for s in unique:
        if s.lower() in existing_skills:
            auto_keep.append(s)
        else:
            need_review.append(s)

    # LLM 只审查未知技能
    filtered = list(auto_keep)
    if need_review:
        prompt = f"""你是技能关键词审查员。审视以下词语，只保留**真正的技术技能**。

输入词语: {", ".join(need_review[:100])}

过滤规则:
1. 保留: 编程语言、框架、库、工具、数据库、操作系统、协议、架构概念
2. 删除: 软技能(沟通/团队)、岗位名(工程师/开发)、公司名、产品名
3. 删除: 过于宽泛的词(熟悉/了解/开发/设计)、残缺碎片
4. 删除: 明显不属于该岗位技术栈的词

只输出保留的词，逗号分隔，不要解释。"""
        with trace("skill_reflect", "LLM 过滤非技能词", model="deepseek-chat") as t:
            try:
                msg = get_utility_llm().invoke(prompt)
                reviewed = [s.strip() for s in msg.content.strip().split(",") if s.strip()]
                filtered.extend(reviewed)
                t["removed"] = len(need_review) - len(reviewed)
                t["kept"] = len(reviewed)
            except Exception:
                filtered.extend(need_review)

    # 语义归一化：将变体匹配到已有标准技能名
    filtered = normalize_skill_list(filtered, registry.embeddings)

    logger.info(
        f">>> skill_reflect: {len(unique)} 去重 → 已知{len(auto_keep)}+LLM保留{len(filtered)-len(auto_keep)} → 最终 {len(filtered)} 个"
    )
    return {"skill_list": filtered}


def save_node(state: AgentState) -> AgentState:
    job_name = normalize_job_name(state["job_name"])
    skill_list = state["skill_list"]
    items = state.get("search_raw_items", []) or []
    total_jds = len(items)

    logger.info(f">>> save_node 入库: {job_name}，共 {len(skill_list)} 个技能（样本 {total_jds} 条 JD）")
    skill_count = Counter(skill_list)
    db.save_skill_list(job_name, skill_count, total_jds=total_jds)
    logger.info(f"<<< save_node 入库完成: {job_name} -> {len(skill_count)} 个不重复技能")
    clear_skill_cache()  # 有新技能入库，刷新语义缓存
    return {"status": "存储完成"}


def store_jd_node(state: AgentState) -> AgentState:
    items = state.get("search_raw_items", []) or []
    if not items:
        logger.warning(">>> store_jd_node: 无结构化搜索结果，跳过")
        return {"status": "JD 入库跳过（无数据）"}

    jd_store = registry.jd_store
    logger.info(f">>> store_jd_node: 入库 {len(items)} 条 JD")
    with trace("store_jd", "JD 入库 + embedding", model="dashscope-v4") as t:
        chunk_count = jd_store.store_jd(job_name=normalize_job_name(state["job_name"]), jd_items=items)
        t["jd_input"] = len(items)
        t["chunks_output"] = chunk_count
    logger.info(f"<<< store_jd_node: 入库完成 -> {chunk_count} 个新 chunk")
    return {"status": f"JD 入库: {chunk_count} 个新 chunk"}


# 构建工作流
workflow = StateGraph(AgentState)
workflow.add_node("search_node", search_node)
workflow.add_node("store_jd_node", store_jd_node)
workflow.add_node("evaluate_node", evaluate_node)
workflow.add_node("extract_node", extract_node)
workflow.add_node("skill_reflect_node", skill_reflect_node)
workflow.add_node("save_node", save_node)

workflow.set_entry_point("search_node")
workflow.add_edge("search_node", "store_jd_node")
workflow.add_edge("store_jd_node", "evaluate_node")
workflow.add_conditional_edges("evaluate_node", route_after_evaluate, {
    "search_node": "search_node",
    "extract_node": "extract_node",
})
workflow.add_edge("extract_node", "skill_reflect_node")
workflow.add_edge("skill_reflect_node", "save_node")
workflow.add_edge("save_node", END)

agent_graph = workflow.compile(checkpointer=create_checkpointer())
