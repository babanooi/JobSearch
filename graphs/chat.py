"""对话 Agent 工作流 —— ChatAgent 理解+决策一体，标记路由回环"""
import uuid
from typing import TypedDict, List

from langgraph.graph import StateGraph, END

from agents.registry import registry
from graphs.analyze import agent_graph as analyze_graph
from memory.short_term import (
    create_checkpointer, compress_history, merge_context, MAX_MESSAGE_ROUNDS,
)
from memory.long_term import (
    query_skill_rank, list_analyzed_jobs, match_job_names,
    hybrid_search_with_rerank, save_conversation, load_latest_summary,
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
    conversation_saved: bool
    chat_round: int  # 当前轮次内第几次调 chat_node（0=首次，1=带检索/分析结果）


def chat_node(state: ChatState) -> ChatState:
    """ChatAgent 一次 LLM 调用：理解+决策+生成回复。通过标记路由后续动作"""
    user_input = state["user_input"]
    summary = state.get("summary", "")
    knowledge = state.get("knowledge", [])
    thread_id = state.get("thread_id", "")
    user_id = state.get("user_id", 0)
    round_num = state.get("chat_round", 0)
    messages = list(state.get("messages", []) or [])

    # 首次对话关联用户
    if user_id and thread_id and not state.get("conversation_saved"):
        try:
            save_conversation(user_id, thread_id, title=user_input[:50])
        except Exception as e:
            logger.warning(f"保存对话关联失败: {e}")

    # 加载长期记忆
    if not summary:
        loaded = load_latest_summary(thread_id)
        if loaded:
            summary = loaded

    # 构建上下文
    context = merge_context(summary, messages, knowledge)

    # ChatAgent 一次调用
    with trace("chat", f"ChatAgent 第{round_num}轮", model="deepseek-chat") as t:
        t["thread_id"] = thread_id
        response, token_usage = registry.chat_agent.reply(user_input, context)
        t["tokens_prompt"] = token_usage["prompt_tokens"]
        t["tokens_completion"] = token_usage["completion_tokens"]

    # 解析标记
    action, arg = registry.chat_agent.parse(response)
    logger.info(f">>> chat_node: action={action} arg={arg}")

    # 追加消息
    new_messages = list(messages)
    new_messages.append({"role": "user", "content": user_input})

    # 压缩
    new_summary = summary
    if len(new_messages) > MAX_MESSAGE_ROUNDS * 2:
        compressed = compress_history(new_messages, MAX_MESSAGE_ROUNDS)
        new_messages = compressed["recent"]
        new_summary = compressed["summary"] or summary

    result = {
        "messages": new_messages,
        "summary": new_summary,
        "conversation_saved": True,
    }

    if action == "analyze":
        pending_job = arg or state.get("pending_job", "") or user_input
        return {
            **result,
            "intent": "analyze",
            "pending_job": pending_job,
            "response": response,
            "chat_round": round_num + 1,
        }
    elif action == "search":
        return {
            **result,
            "intent": "search",
            "response": response,
            "chat_round": round_num + 1,
        }
    else:  # chat - 普通对话
        new_messages.append({"role": "assistant", "content": response})
        return {
            **result,
            "intent": "chat",
            "messages": new_messages,
            "response": response,
            "chat_round": 0,
        }


def route_after_chat(state: ChatState) -> str:
    intent = state.get("intent", "")
    if intent == "analyze":
        return "trigger_analyze"
    elif intent == "search":
        return "rag_query"
    return "end"


def rag_query_node(state: ChatState) -> ChatState:
    user_input = state["user_input"]
    summary = state.get("summary", "")
    search_query = f"{summary}\n{user_input}" if summary else user_input

    logger.info(f">>> rag_query: {user_input[:50]}")
    knowledge = []

    with trace("rag_query", "混合检索", model="") as t:
        t["thread_id"] = state.get("thread_id", "")

        # MySQL 排名
        try:
            matched = match_job_names(search_query, registry.embeddings)
            for job_name in matched:
                skills = query_skill_rank(job_name, top_n=5)
                if skills:
                    lines = [f"**{job_name}** 技能 Top{len(skills)}:"]
                    for s in skills:
                        lines.append(f"  - {s['skill']} (出现 {s['count']} 次, 样本 {s.get('total_jds', '?')} 条 JD)")
                    knowledge.append("\n".join(lines))
        except Exception as e:
            logger.warning(f"MySQL 查询失败: {e}")

        # BM25+向量+RRF
        try:
            jd_results = hybrid_search_with_rerank(search_query, registry.embeddings, top_k=3)
            for r in jd_results:
                score_info = f"(RRF:{r.get('rrf_score', '?')})"
                knowledge.append(f"[{r['job_name']} | {r['company']} {score_info}] {r['text'][:500]}")
            logger.info(f"  hybrid_search: {len(jd_results)} 条")
        except Exception as e:
            logger.warning(f"语义检索失败: {e}")

    return {"knowledge": knowledge}


def trigger_analyze_node(state: ChatState) -> ChatState:
    pending = state.get("pending_job", "")
    user_input = state["user_input"]
    job_name = pending or user_input
    search_query = f"{job_name} 招聘要求 技术栈 技能 岗位职责"
    thread_id = state.get("thread_id", str(uuid.uuid4()))

    logger.info(f">>> trigger_analyze: job={job_name}")

    with trace("trigger_analyze", "执行分析工作流", model="deepseek-v4-pro+chat") as t:
        t["thread_id"] = thread_id
        t["job_name"] = job_name
        result = analyze_graph.invoke(
            {"job_name": job_name, "search_query": search_query, "status": "开始执行"},
            config={"configurable": {"thread_id": thread_id}},
        )
        t["skills_count"] = len(result.get("skill_list", []))

    # 格式化分析结果为 knowledge
    knowledge = []
    try:
        skills = query_skill_rank(job_name, top_n=10)
        if skills:
            lines = [f"**{job_name}** 最新技能需求 Top{len(skills)}:"]
            for i, s in enumerate(skills, 1):
                lines.append(f"  {i}. {s['skill']} (出现 {s['count']} 次)")
            knowledge.append("\n".join(lines))
    except Exception as e:
        knowledge.append(f"分析完成但查询结果失败: {e}")

    return {"knowledge": knowledge, "response": ""}


# ═══ 构建工作流 ═══
chat_workflow = StateGraph(ChatState)
chat_workflow.add_node("chat_node", chat_node)
chat_workflow.add_node("rag_query", rag_query_node)
chat_workflow.add_node("trigger_analyze", trigger_analyze_node)

chat_workflow.set_entry_point("chat_node")
chat_workflow.add_conditional_edges("chat_node", route_after_chat, {
    "rag_query": "rag_query",
    "trigger_analyze": "trigger_analyze",
    "end": END,
})
chat_workflow.add_edge("rag_query", "chat_node")        # 检索结果喂回 chat_node
chat_workflow.add_edge("trigger_analyze", "chat_node")  # 分析结果喂回 chat_node

chat_agent_graph = chat_workflow.compile(checkpointer=create_checkpointer())


def new_thread_id() -> str:
    return str(uuid.uuid4())
