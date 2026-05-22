"""对话调度 Agent —— LLM 自主判断：分析 / 检索 / 确认，统一决策"""
from agents.base import get_utility_llm
from langchain_core.prompts import PromptTemplate
from core.logger import get_logger

logger = get_logger(__name__)

SUPERVISOR_PROMPT = PromptTemplate.from_template("""
你是对话调度员。根据上下文决定下一步动作，只输出一行指令。

可选动作:
- analyze|<岗位名>     → 用户要分析搜索某个岗位
- confirm_analyze     → 用户回复"好的/可以"，确认上一轮建议
- query|structured    → 问技能排名/出现次数
- query|semantic      → 问具体技术怎么用/框架关系
- query|hybrid        → 既要排名概览又要JD来源
- query|meta          → 问有哪些岗位/公司

当前上下文:
- 用户消息: {user_input}
- 待分析岗位: {pending_job}
- 历史摘要: {summary}
- 已分析岗位: {analyzed_jobs}

只输出一条指令，不要解释。
""")


class ChatSupervisor:
    def decide(
        self,
        user_input: str,
        pending_job: str = "",
        summary: str = "",
        analyzed_jobs: list[str] | None = None,
    ) -> dict:
        """返回 {"intent": str, "pending_job": str, "tokens": dict}"""
        msg = get_utility_llm().invoke(SUPERVISOR_PROMPT.invoke({
            "user_input": user_input,
            "pending_job": pending_job or "(无)",
            "summary": summary or "(无)",
            "analyzed_jobs": "、".join(analyzed_jobs) if analyzed_jobs else "(无)",
        }))
        raw = msg.content.strip()
        usage = msg.response_metadata.get("token_usage", {})
        tokens = {"prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0)}
        logger.info(f"ChatSupervisor: {raw}")

        if raw.startswith("confirm_analyze") and pending_job:
            return {"intent": "analyze", "pending_job": pending_job, "tokens": tokens}
        if raw.startswith("analyze|"):
            return {"intent": "analyze", "pending_job": raw.split("|", 1)[1].strip(), "tokens": tokens}
        if raw.startswith("query|"):
            return {"intent": raw, "pending_job": "", "tokens": tokens}
        if "analyze" in raw.lower():
            return {"intent": "analyze", "pending_job": "", "tokens": tokens}
        return {"intent": "query|hybrid", "pending_job": "", "tokens": tokens}
