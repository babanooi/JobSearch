"""求职研究工作流 —— 拆解需求 → 并行执行 → 聚合卡片"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from langgraph.graph import StateGraph, END

from agents.registry import registry
from agents.base import get_utility_llm
from memory.short_term import create_checkpointer
from memory.long_term import query_skill_rank, match_job_names
from core.logger import get_logger
from core.tracer import trace

logger = get_logger(__name__)


def research_plan_node(state: dict) -> dict:
    """ChatAgent 拆解用户需求为子任务列表"""
    user_input = state["user_input"]
    messages = state.get("messages", []) or []

    # 取最近的对话上下文
    context = "\n".join(
        f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:200]}"
        for m in messages[-6:]
    )

    prompt = f"""你是求职研究规划师。根据用户需求，拆解为子任务。只输出 JSON 数组，不要解释。

可用任务类型:
- analyze: 搜索JD并提取技能排名（耗时较长，60s+）
- search: 定向互联网搜索（快速，2-3s）

对话上下文:
{context}

用户需求: {user_input}

输出格式示例:
[{{"type":"analyze","label":"技能需求","query":"Python后端 招聘 技能"}},
 {{"type":"search","label":"薪资范围","query":"Python后端 深圳 薪资范围"}},
 {{"type":"search","label":"面试准备","query":"Python后端 面试题 高频考点"}}]

只输出 JSON 数组。"""

    with trace("research_plan", "拆解研究子任务", model="deepseek-chat") as t:
        try:
            import json
            raw = get_utility_llm().invoke(prompt).content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("\n", 1)[0]
            plan = json.loads(raw)
        except Exception:
            # 兜底：默认 analyze
            plan = [{"type": "analyze", "label": "技能需求", "query": user_input}]

        t["subtasks"] = len(plan)

    logger.info(f">>> research_plan: {len(plan)} 个子任务")
    for p in plan:
        logger.info(f"    [{p['type']}] {p['label']}: {p['query'][:50]}")

    return {"research_plan": plan, "research_cards": []}


def parallel_execute_node(state: dict) -> dict:
    """ThreadPoolExecutor 并行执行所有子任务"""
    plan = state.get("research_plan", [])
    if not plan:
        return {"research_cards": []}

    cards = []
    logger.info(f">>> parallel_execute: {len(plan)} 个子任务并行执行")

    def run_subtask(task: dict) -> dict:
        t0 = time.time()
        ttype = task["type"]
        label = task["label"]
        query = task["query"]

        with trace(f"research_{ttype}", label, model="" if ttype != "analyze" else "v4-pro") as t:
            t["query"] = query

            if ttype == "analyze":
                try:
                    matched = match_job_names(query, registry.embeddings)
                    if matched:
                        job = matched[0]
                        skills = query_skill_rank(job, top_n=5)
                        total_jds = skills[0].get("total_jds", 0) if skills else 0
                        items = [f"{s['skill']}({s['count']}次)" for s in skills]
                        source = f"基于已有数据 {total_jds} 条JD" if total_jds else ""
                        logger.info(f"    analyze 命中已有数据: {job} ({len(skills)}技能)")
                    else:
                        # 无缓存时退回快速搜索，不跑完整分析（避免 3-5min 延迟）
                        items_raw = registry.search_tool.search_job_info(query)
                        items = [r.get("title", r.get("content", "")[:120]) for r in items_raw[:5]]
                        source = f"AnySearch 搜索: {query[:40]}（该岗位尚未分析，可稍后单独分析）"
                        logger.info(f"    analyze 无缓存，退回搜索: {len(items_raw)} 条结果")
                except Exception as e:
                    items = [f"分析失败: {e}"]
                    source = ""
            else:
                try:
                    items_raw = registry.search_tool.search_job_info(query)
                    items = [r.get("title", r.get("content", "")[:120]) for r in items_raw[:5]]
                    source = f"AnySearch 搜索: {query[:40]}"
                except Exception as e:
                    items = [f"搜索失败: {e}"]
                    source = ""

            t["items"] = len(items)
            t["elapsed"] = f"{time.time() - t0:.1f}s"

        return {"section": label, "items": items, "source": source}

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(run_subtask, t): t for t in plan}
        for f in as_completed(futures):
            cards.append(f.result())

    # 保持原顺序
    label_order = [t["label"] for t in plan]
    cards.sort(key=lambda c: label_order.index(c["section"]) if c["section"] in label_order else 99)

    logger.info(f"<<< parallel_execute: {len(cards)} 张卡片完成")
    return {"research_cards": cards}


def reflect_node(state: dict) -> dict:
    """Self-Reflection：审视卡片完整性，有缺口则生成补搜子任务（最多1轮）"""
    cards = state.get("research_cards", [])
    user_input = state.get("user_input", "")
    reflect_round = state.get("reflect_round", 0)
    max_rounds = 1

    if reflect_round >= max_rounds or not cards:
        return {"intent": "research_done", "reflect_round": reflect_round}

    import json
    card_summary = "\n".join(
        f"- {c['section']}: {len(c.get('items',[]))}条 ({c.get('source','')})"
        for c in cards
    )

    prompt = f"""你是求职研究质量审查员。审视以下调研结果，判断是否完整。

用户需求: {user_input}

当前结果:
{card_summary}

判断标准:
1. 是否覆盖了技能/薪资/公司/面试等关键维度？
2. 每个维度的数据量是否充分（≥3条）？
3. 对求职者是否有实际指导意义？

如果完整，输出: FINISH
如果有缺口，输出 JSON 数组（最多3个）:
[{{"type":"search","label":"维度名","query":"搜索词"}}]

只输出 FINISH 或 JSON 数组。"""

    with trace("reflect", "反思补全校验", model="deepseek-chat") as t:
        try:
            raw = get_utility_llm().invoke(prompt).content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("\n", 1)[0]
        except Exception:
            raw = "FINISH"

    new_round = reflect_round + 1

    if raw.strip().upper() == "FINISH":
        logger.info(f">>> reflect: 信息完整，结束研究")
        return {
            "intent": "research_done",
            "reflect_round": new_round,
            "knowledge": state.get("knowledge", []),
            "response": state.get("response", ""),
        }

    try:
        extra_plan = json.loads(raw)
        logger.info(f">>> reflect: 发现缺口，追加 {len(extra_plan)} 个子任务")
        for p in extra_plan:
            logger.info(f"    + [{p.get('type','?')}] {p.get('label','?')}: {p.get('query','?')[:50]}")

        # 合并到现有 research_plan，保留已有 knowledge
        existing_plan = state.get("research_plan", [])
        return {
            "research_plan": existing_plan + extra_plan,
            "reflect_round": new_round,
            "knowledge": state.get("knowledge", []),
            "response": state.get("response", ""),
        }
    except Exception:
        return {
            "intent": "research_done",
            "reflect_round": new_round,
            "knowledge": state.get("knowledge", []),
            "response": state.get("response", ""),
        }


def route_after_reflect(state: dict) -> str:
    if state.get("intent") == "research_done":
        return "end"
    return "parallel_execute"


def synthesize_node(state: dict) -> dict:
    """聚合卡片结果，生成结构化 JSON 存入 knowledge"""
    cards = state.get("research_cards", [])
    if not cards:
        return {"knowledge": [], "response": "研究未产生结果"}

    # 构建卡片展示用的 knowledge
    knowledge = []
    for card in cards:
        section = card["section"]
        items = card.get("items", [])
        source = card.get("source", "")

        lines = [f"## {section}"]
        for item in items[:8]:
            lines.append(f"- {item}")
        if source:
            lines.append(f"\n*{source}*")
        knowledge.append("\n".join(lines))

    # 生成简短总结
    summary_parts = [f"共完成 {len(cards)} 项调研："]
    for card in cards:
        summary_parts.append(f"- {card['section']}: {len(card.get('items',[]))} 条结果")

    response = "\n".join(summary_parts)

    return {
        "knowledge": knowledge,
        "response": response,
        "research_cards": cards,
        "reflect_round": state.get("reflect_round", 0),
    }


# ═══ 构建工作流 ═══
research_workflow = StateGraph(dict)
research_workflow.add_node("research_plan", research_plan_node)
research_workflow.add_node("parallel_execute", parallel_execute_node)
research_workflow.add_node("synthesize", synthesize_node)
research_workflow.add_node("reflect", reflect_node)

research_workflow.set_entry_point("research_plan")
research_workflow.add_edge("research_plan", "parallel_execute")
research_workflow.add_edge("parallel_execute", "synthesize")
research_workflow.add_edge("synthesize", "reflect")
research_workflow.add_conditional_edges("reflect", route_after_reflect, {
    "parallel_execute": "parallel_execute",
    "end": END,
})

research_graph = research_workflow.compile(checkpointer=create_checkpointer())
