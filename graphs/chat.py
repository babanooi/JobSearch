"""对话 Agent 工作流 —— Supervisor 调度 → 分析 / 检索 → 生成回复"""
import uuid
import re
from typing import TypedDict, List

from langgraph.graph import StateGraph, END
from langchain_core.prompts import PromptTemplate

from agents.registry import registry
from agents.base import get_utility_llm
from graphs.analyze import agent_graph as analyze_graph
from memory.short_term import (
    create_checkpointer, compress_history, merge_context, MAX_MESSAGE_ROUNDS,
    prune_old_checkpoints,
)
from memory.long_term import (
    query_skill_rank, list_analyzed_jobs,
    match_job_names, hybrid_search_with_rerank,
    save_summary, load_latest_summary, save_conversation,
)
from core.logger import get_logger
from core.tracer import trace

logger = get_logger(__name__)


class ChatState(TypedDict):
    thread_id: str
    user_id: int
    messages: List[dict]
    summary: str
    user_input: str
    intent: str
    knowledge: List[str]
    response: str
    pending_job: str


def supervise_node(state: ChatState) -> ChatState:
    """调用 ChatSupervisor Agent，一次 LLM 调用统一决策"""
    try:
        analyzed = list_analyzed_jobs()
    except Exception:
        analyzed = []

    # 新对话时，关联到当前用户
    user_id = state.get("user_id", 0)
    thread_id = state.get("thread_id", "")
    if user_id and thread_id:
        try:
            save_conversation(user_id, thread_id, title=state["user_input"][:50])
        except Exception as e:
            logger.warning(f"保存对话关联失败: {e}")

    # 新对话或恢复对话时，从 MySQL 加载历史摘要
    summary = state.get("summary", "")
    if not summary:
        loaded = load_latest_summary(thread_id)
        if loaded:
            summary = loaded
            logger.info(f"从 MySQL 恢复历史摘要: {len(summary)} 字")

    with trace("supervise", "对话意图路由", model="deepseek-chat") as t:
        decision = registry.supervisor.decide(
            user_input=state["user_input"],
            pending_job=state.get("pending_job", ""),
            summary=summary,
            analyzed_jobs=analyzed,
        )
        t["thread_id"] = thread_id
        t["intent"] = decision["intent"]
        t["tokens_prompt"] = decision["tokens"].get("prompt_tokens", 0)
        t["tokens_completion"] = decision["tokens"].get("completion_tokens", 0)
    return {"intent": decision["intent"], "pending_job": decision["pending_job"], "summary": summary}


def route_after_supervise(state: ChatState) -> str:
    intent = state.get("intent", "")
    if "analyze" in intent:
        return "trigger_analyze"
    return "rag_query"


def rag_query_node(state: ChatState) -> ChatState:
    user_input = state["user_input"]
    summary = state.get("summary", "")
    intent = state.get("intent", "query|hybrid")

    qtype = intent.split("|")[1] if "|" in intent else "hybrid"
    search_query = f"{summary}\n{user_input}" if summary else user_input

    with trace("rag_query", f"检索 [{qtype}]", model="") as t:
        t["thread_id"] = state.get("thread_id", "")

        logger.info(f">>> rag_query [{qtype}]: {user_input[:50]}")

        knowledge = []

        if qtype in ("structured", "hybrid"):
            try:
                matched = match_job_names(search_query, registry.embeddings)
                for job_name in matched:
                    skills = query_skill_rank(job_name, top_n=5)
                    if skills:
                        lines = [f"**{job_name}** 技能 Top{len(skills)}:"]
                        for s in skills:
                            lines.append(f"  - {s['skill']} (出现 {s['count']} 次)")
                        knowledge.append("\n".join(lines))
            except Exception as e:
                logger.warning(f"  MySQL 查询失败: {e}")

        if qtype in ("semantic", "hybrid"):
            try:
                chroma_query = search_query
                if qtype == "hybrid" and knowledge:
                    top_skills = []
                    for k in knowledge:
                        for line in k.split("\n"):
                            if line.strip().startswith("-"):
                                top_skills.append(line.split("(")[0].strip("- "))
                    if top_skills:
                        chroma_query = " ".join(top_skills[:5])

                jd_results = hybrid_search_with_rerank(
                    chroma_query, registry.embeddings, top_k=3
                )
                for r in jd_results:
                    score_info = f"(RRF:{r.get('rrf_score', '?')}, cos:{r.get('cos_sim', '?')})"
                    knowledge.append(
                        f"[{r['job_name']} | {r['company']} {score_info}] {r['text'][:500]}"
                    )
                logger.info(f"  hybrid_search: {len(jd_results)} 条")
            except Exception as e:
                logger.warning(f"  语义检索失败: {e}")

        if qtype == "meta":
            try:
                jobs = list_analyzed_jobs()
                if jobs:
                    knowledge.append("已分析岗位: " + "、".join(jobs[:20]))
            except Exception:
                pass

        pending = ""
        if not knowledge and qtype != "meta":
            try:
                chain = (
                    PromptTemplate.from_template("从以下输入提取岗位名: {text}\n只输出岗位名。")
                    | get_utility_llm()
                )
                pending = chain.invoke({"text": user_input}).content.strip()
            except Exception:
                pending = ""
            if not pending:
                pending = user_input
            knowledge.append(f"「{pending}」还没有分析数据，要我帮你分析吗？")

        t["knowledge_items"] = len(knowledge)
        t["qtype"] = qtype

    return {"knowledge": knowledge, "pending_job": pending}


def generate_response_node(state: ChatState) -> ChatState:
    messages = state.get("messages", [])
    user_input = state["user_input"]
    summary = state.get("summary", "")
    knowledge = state.get("knowledge", [])

    context = merge_context(summary, messages, knowledge)
    with trace("generate_response", "ChatAgent 生成回复", model="deepseek-chat") as t:
        t["thread_id"] = state.get("thread_id", "")
        response, token_usage = registry.chat_agent.reply(user_input, context)
        t["response_len"] = len(response)
        t["tokens_prompt"] = token_usage["prompt_tokens"]
        t["tokens_completion"] = token_usage["completion_tokens"]

    new_messages = list(messages) if messages else []
    new_messages.append({"role": "user", "content": user_input})
    new_messages.append({"role": "assistant", "content": response})

    new_summary = summary
    if len(new_messages) > MAX_MESSAGE_ROUNDS * 2:
        compressed = compress_history(new_messages, MAX_MESSAGE_ROUNDS)
        new_messages = compressed["recent"]
        new_summary = compressed["summary"] or summary
        # 压缩后的摘要写入 MySQL，跨会话持久化
        if new_summary:
            try:
                save_summary(state.get("thread_id", ""), new_summary)
            except Exception as e:
                logger.warning(f"摘要写入 MySQL 失败: {e}")
        # 清理 SqliteSaver 旧快照，只保留压缩后的当前状态
        try:
            prune_old_checkpoints(state.get("thread_id", ""))
        except Exception as e:
            logger.warning(f"checkpoint 清理失败: {e}")

    return {"messages": new_messages, "response": response, "summary": new_summary}


def trigger_analyze_node(state: ChatState) -> ChatState:
    user_input = state["user_input"]
    messages = list(state.get("messages", []) or [])
    pending = state.get("pending_job", "")

    # 岗位名：Supervisor 已填充 pending_job
    job_name = pending or user_input
    search_query = f"{job_name} 招聘要求 技术栈 技能 岗位职责"

    logger.info(f">>> trigger_analyze: job={job_name}")

    messages.append({"role": "user", "content": user_input})
    messages.append({
        "role": "assistant",
        "content": f"正在为你分析「{job_name}」的最新招聘技能需求，请稍等..."
    })

    try:
        with trace("trigger_analyze", "执行分析工作流", model="deepseek-v4-pro+chat") as t:
            t["thread_id"] = state.get("thread_id", "")
            t["job_name"] = job_name
            result = analyze_graph.invoke(
                {"job_name": job_name, "search_query": search_query, "status": "开始执行"},
                config={"configurable": {"thread_id": state.get("thread_id", str(uuid.uuid4()))}},
            )
            t["skills_count"] = len(result.get("skill_list", []))
            t["jd_items"] = len(result.get("search_raw_items", []))
            logger.info(f"<<< analyze 完成: {t['skills_count']} 个技能")
    except Exception as e:
        logger.error(f"analyze 失败: {e}")
        messages.append({"role": "assistant", "content": f"分析失败: {e}"})
        return {"messages": messages, "response": f"分析失败: {e}"}

    try:
        skills = query_skill_rank(job_name, top_n=10)
        if skills:
            lines = [f"**{job_name}** 最新技能需求 Top{len(skills)}:"]
            for i, s in enumerate(skills, 1):
                lines.append(f"  {i}. {s['skill']} (出现 {s['count']} 次)")
            response = "\n".join(lines)
        else:
            response = f"已分析「{job_name}」，但未能提取到技能关键词，请尝试更具体的岗位名。"
    except Exception as e:
        response = f"分析完成但查询结果失败: {e}"

    messages.append({"role": "assistant", "content": response})
    return {"messages": messages, "response": response}


# 构建工作流：supervise → (rag_query | trigger_analyze) → generate_response
chat_workflow = StateGraph(ChatState)
chat_workflow.add_node("supervise", supervise_node)
chat_workflow.add_node("rag_query", rag_query_node)
chat_workflow.add_node("trigger_analyze", trigger_analyze_node)
chat_workflow.add_node("generate_response", generate_response_node)

chat_workflow.set_entry_point("supervise")
chat_workflow.add_conditional_edges("supervise", route_after_supervise, {
    "rag_query": "rag_query",
    "trigger_analyze": "trigger_analyze",
})
chat_workflow.add_edge("rag_query", "generate_response")
chat_workflow.add_edge("trigger_analyze", END)
chat_workflow.add_edge("generate_response", END)

chat_agent_graph = chat_workflow.compile(checkpointer=create_checkpointer())


def new_thread_id() -> str:
    return str(uuid.uuid4())
