from agents.registry import registry
from graph.state import AgentState
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from collections import Counter
from langchain.prompts import PromptTemplate
from utils.logger import get_logger

search_agent = registry.search_agent
extract_agent = registry.extract_agent
db = registry.db_tool

logger = get_logger(__name__)

MAX_SEARCH_ROUNDS = 10

#定义工作节点
def normalize_node(state: AgentState) -> AgentState:
    """入口节点：将模糊岗位名标准化为搜索关键词"""
    logger.info(f">>> normalize_node 标准化: {state['job_name']}")
    NORMALIZE_PROMPT = PromptTemplate.from_template(
    """
     你是一位招聘行业专家。用户输入了一个模糊的岗位名称，你需要将其扩展为精准的搜索关键词。

     规则：
     1. 补全岗位的标准行业名称（如"后端"→"后端开发工程师"）
     2. 附加招聘相关术语：招聘要求、技术栈、技能、岗位职责
     3. 如果用户输入本身已很精确，直接复述即可
     4. 只输出搜索关键词，不要句子，不要解释

     用户输入: {job_name}
     输出:
     """)
    job_name = state["job_name"]
    chain = NORMALIZE_PROMPT | extract_agent.llm
    query = chain.invoke({"job_name": job_name}).content.strip()
    logger.info(f"<<< normalize_node 结果: {query}")
    return {
        "normalized_query": query,
        "status": f"搜索词已标准化: {query}"
    }

def search_node(state: AgentState) -> AgentState:
    """搜索节点：根据 query 搜索，结果追加到已收集列表"""
    raw_query = state.get("search_query", "")
    if raw_query.startswith("SEARCH|"):
        query = raw_query.split("|", 1)[1].strip()
    else:
        query = state.get("normalized_query") or state["job_name"]

    round_num = state.get("search_round", 0) + 1
    logger.info(f">>> search_node 第{round_num}轮搜索: {query}")

    new_content = search_agent.run(query)

    collected = list(state.get("search_content") or [])
    collected.append(new_content)

    logger.info(f"<<< search_node 第{round_num}轮完成，已收集 {len(collected)} 组结果")
    return {
        "search_content": collected,
        "search_round": round_num,
        "search_query": raw_query,
        "status": "搜索完成"
    }

def evaluate_node(state: AgentState) -> AgentState:
      """LLM 评估信息是否充分"""
      round_num = state.get("search_round", 0)
      logger.info(f">>> evaluate_node 第{round_num}轮评估中...")

      prompt = PromptTemplate.from_template(
      """
      你是招聘数据分析专家。判断当前搜索结果是否足够提取"{job_name}"岗位的技能。

      已收集{round_num}轮，上限{max_rounds}轮。
      已收集的招聘信息:
      {collected}

      信息足够则输出 FINISH，需要补搜则输出: SEARCH|<补搜关键词>
      只输出 FINISH 或 SEARCH|<关键词>，不要其他内容。
      """)

      llm = search_agent.llm
      chain = prompt | llm
      decision = chain.invoke({
          "job_name": state["job_name"],
          "round_num": state.get("search_round", 0),
          "max_rounds": MAX_SEARCH_ROUNDS,
          "collected": "\n---\n".join(state.get("search_content", [])[-6:]),
      }).content.strip()

      logger.info(f"<<< evaluate_node 决策: {decision}")
      return {"status": f"评估结果: {decision}", "search_query": decision}

# 路由函数
def route_after_evaluate(state: AgentState) -> str:
      decision = state.get("search_query", "")
      if state.get("search_round", 0) >= MAX_SEARCH_ROUNDS:
          logger.info(f"▸ 路由: 已达最大轮次 → extract_node")
          return "extract_node"
      if decision.startswith("FINISH"):
          logger.info(f"▸ 路由: 评估充分 → extract_node")
          return "extract_node"
      if decision.startswith("SEARCH|"):
          logger.info(f"▸ 路由: 需要补搜 → search_node")
          return "search_node"
      logger.warning(f"▸ 路由: 无法解析决策，兜底 → extract_node")
      return "extract_node"

def extract_node(state: AgentState) -> AgentState:
    """抽取节点，调用extract_agent
    从多条招聘信息中，逐条提取技能，全部合并成一个大列表
    """
    job_descriptions = state["search_content"]
    logger.info(f">>> extract_node 开始提取技能，共 {len(job_descriptions)} 条招聘信息")

    combined = "\n\n---\n\n".join(job_descriptions)
    all_skills = extract_agent.run(combined)
    logger.info(f"<<< extract_node 完成 → 提取到 {len(all_skills)} 个技能")

    # 返回合并后的所有技能
    return {"skill_list": all_skills}

def save_node(state: AgentState) -> AgentState:
    """存储节点，调用数据库统计岗位-技能-出现次数"""
    job_name = state['job_name']
    skill_list = state['skill_list']
    logger.info(f">>> save_node 入库: {job_name}，共 {len(skill_list)} 个技能")

    skill_count = Counter(skill_list)

    db.save_skill_list(job_name, skill_count)
    logger.info(f"<<< save_node 入库完成: {job_name} → {len(skill_count)} 个不重复技能")
    return { "status": "存储完成"}

#构建工作流
workflow = StateGraph(AgentState)
#添加节点
workflow.add_node("normalize_node",normalize_node)
workflow.add_node("search_node",search_node)
workflow.add_node("evaluate_node", evaluate_node)
workflow.add_node("extract_node",extract_node)
workflow.add_node("save_node",save_node)

#设置流程流转（固定工作流：搜索 → 抽取 → 保存）
workflow.set_entry_point("normalize_node")
workflow.add_edge("normalize_node", "search_node")
workflow.add_edge("search_node", "evaluate_node")
#动态条件边 react核心
workflow.add_conditional_edges("evaluate_node", route_after_evaluate, {
    "search_node": "search_node",
    "extract_node": "extract_node",
})
workflow.add_edge("extract_node", "save_node")
workflow.add_edge("save_node", END)
#编译工作流
checkpointer = MemorySaver()
agent_graph = workflow.compile(checkpointer=checkpointer)