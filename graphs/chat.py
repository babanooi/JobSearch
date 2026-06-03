"""对话 Agent 工作流 —— ChatAgent 理解+决策一体，标记路由回环"""
import re
import uuid
from typing import TypedDict, List

from langgraph.graph import StateGraph, END

from agents.registry import registry
from graphs.analyze import agent_graph as analyze_graph
from graphs.research import research_graph
from memory.short_term import (
    create_checkpointer, compress_history, merge_context, MAX_MESSAGE_ROUNDS,
)
from memory.long_term import (
    query_skill_rank, list_analyzed_jobs, match_job_names,
    hybrid_search_with_rerank, save_conversation, load_latest_summary,
    save_summary,
)
from tools.skill_guard import normalize_job_name
from core.task_manager import TaskCancelledError
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
    source_index: List[dict]  # 来源元数据 [{idx, type, job, company, url}, ...]
    response: str
    pending_job: str
    conversation_saved: bool
    chat_round: int  # 当前轮次内第几次调 chat_node（0=首次，1=带检索/分析结果）
    task: object       # Task 实例，用于取消检查


def chat_node(state: ChatState) -> ChatState:
    """ChatAgent 一次 LLM 调用：理解+决策+生成回复。通过标记路由后续动作"""
    # 取消检查：开头就检查，避免浪费 LLM 调用
    task = state.get("task")
    if task and task.is_cancelled():
        raise TaskCancelledError(f"任务 {task.task_id} 已取消")
    if task:
        task.progress = "分析意图..."

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

    # 追加消息（只在首次进入时追加用户消息，避免重复）
    new_messages = list(messages)
    if round_num == 0:
        new_messages.append({"role": "user", "content": user_input})

    # 压缩
    new_summary = summary
    if len(new_messages) > MAX_MESSAGE_ROUNDS * 2:
        total_before = len(new_messages) // 2
        compressed = compress_history(new_messages, MAX_MESSAGE_ROUNDS, previous_summary=summary)
        new_messages = compressed["recent"]
        new_summary = compressed["summary"] or summary
        if new_summary:
            end_round = total_before - MAX_MESSAGE_ROUNDS
            save_summary(thread_id, new_summary, start_round=1, end_round=end_round)

    result = {
        "messages": new_messages,
        "summary": new_summary,
        "conversation_saved": True,
    }

    # 防止无限循环：已有 knowledge 且非首次进入时，强制 chat 不再触发检索/分析/研究
    if knowledge and round_num > 0 and action in ("search", "analyze", "research"):
        logger.info(f">>> 已有 knowledge，忽略 {action} 标记，强制 chat")
        action = "chat"

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
    elif action == "research":
        return {
            **result,
            "intent": "research",
            "response": response,
            "chat_round": round_num + 1,
        }
    else:  # chat - 普通对话
        if knowledge:
            response, unverified = registry.chat_agent.verify_citations(response, knowledge)
            if unverified:
                response = registry.chat_agent.apply_corrections(response, unverified)
        # 清洗内部路由标记，避免泄漏到前端
        response = re.sub(r'\n?\[(SEARCH|ANALYZE|RESEARCH):[^\]]*\]', '', response).strip()
        new_messages.append({"role": "assistant", "content": response})
        return {
            **result,
            "intent": "chat",
            "messages": new_messages,
            "response": response,
            "chat_round": 0,
        }


def research_node(state: ChatState) -> ChatState:
    """调用研究工作流：拆解 → 并行执行 → 聚合卡片"""
    user_input = state["user_input"]
    thread_id = state.get("thread_id", "")

    logger.info(f">>> research: {user_input[:50]}")
    with trace("research", "执行研究工作流", model="deepseek-chat+v4-pro") as t:
        t["thread_id"] = thread_id
        result = research_graph.invoke(
            {"user_input": user_input, "messages": state.get("messages", [])},
            config={"configurable": {"thread_id": f"research_{thread_id}"}},
        )
        t["cards"] = len(result.get("research_cards", []))

    return {
        "knowledge": result.get("knowledge", []),
        "response": result.get("response", ""),
    }


def route_after_chat(state: ChatState) -> str:
    intent = state.get("intent", "")
    if intent == "analyze":
        return "trigger_analyze"
    elif intent == "search":
        return "rag_query"
    elif intent == "research":
        return "research"
    return "end"


def rag_query_node(state: ChatState) -> ChatState:
    user_input = state["user_input"]
    summary = state.get("summary", "")
    search_query = f"{summary}\n{user_input}" if summary else user_input

    logger.info(f">>> rag_query: {user_input[:50]}")
    task = state.get("task")
    if task: task.progress = "检索知识库..."
    knowledge = []
    source_index = []

    with trace("rag_query", "混合检索", model="") as t:
        t["thread_id"] = state.get("thread_id", "")

        # MySQL 排名
        try:
            matched = match_job_names(search_query, registry.embeddings)
            for job_name in matched:
                skills = query_skill_rank(job_name, top_n=5)
                if skills:
                    idx = len(knowledge) + 1
                    lines = [f"[{idx}] **{job_name}** 技能 Top{len(skills)}:"]
                    for s in skills:
                        lines.append(f"  - {s['skill']} (出现 {s['count']} 次, 样本 {s.get('total_jds', '?')} 条 JD)")
                    knowledge.append("\n".join(lines))
                    source_index.append({"idx": idx, "type": "skill_rank", "job": job_name})
        except Exception as e:
            logger.warning(f"MySQL 查询失败: {e}")

        # BM25+向量+RRF
        try:
            jd_results = hybrid_search_with_rerank(search_query, registry.embeddings, top_k=3)
            for r in jd_results:
                idx = len(knowledge) + 1
                url = r.get('source_url', '')
                knowledge.append(f"[{idx}] 来源: {r['company']} | {r['job_name']}\n链接: {url}\n摘要: {r['text'][:400]}")
                source_index.append({"idx": idx, "type": "jd", "company": r['company'], "job": r['job_name'], "url": url})
            logger.info(f"  hybrid_search: {len(jd_results)} 条")
        except Exception as e:
            logger.warning(f"语义检索失败: {e}")

    return {"knowledge": knowledge, "source_index": source_index}


def trigger_analyze_node(state: ChatState) -> ChatState:
    pending = state.get("pending_job", "")
    user_input = state["user_input"]
    job_name = normalize_job_name(pending or user_input)
    search_query = f"{job_name} 招聘要求 技术栈 技能 岗位职责"
    thread_id = state.get("thread_id", str(uuid.uuid4()))

    logger.info(f">>> trigger_analyze: job={job_name}")
    task = state.get("task")
    if task: task.progress = f"分析岗位: {job_name}..."

    with trace("trigger_analyze", "执行分析工作流", model="deepseek-v4-pro+chat") as t:
        t["thread_id"] = thread_id
        t["job_name"] = job_name
        result = analyze_graph.invoke(
            {"job_name": job_name, "search_query": search_query, "status": "开始执行", "task": state.get("task")},
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
chat_workflow.add_node("research", research_node)

chat_workflow.set_entry_point("chat_node")
chat_workflow.add_conditional_edges("chat_node", route_after_chat, {
    "rag_query": "rag_query",
    "trigger_analyze": "trigger_analyze",
    "research": "research",
    "end": END,
})
chat_workflow.add_edge("rag_query", "chat_node")
chat_workflow.add_edge("trigger_analyze", "chat_node")
chat_workflow.add_edge("research", "chat_node")

chat_agent_graph = chat_workflow.compile(checkpointer=create_checkpointer())


def new_thread_id() -> str:
    return str(uuid.uuid4())
