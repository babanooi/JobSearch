"""对话 Agent —— LLM 生成回复（轻量模型 deepseek-chat）"""
from agents.base import get_utility_llm
from core.logger import get_logger

logger = get_logger(__name__)

CHAT_SYSTEM_PROMPT = """你是求职助手，帮用户分析岗位技能需求。回答规则：

1. 如果上下文中包含 JD 数据或技能排名，**必须引用具体公司/URL/技能名作为依据**
2. 当用户问"某某岗位需要什么技能"时，优先使用技能排名数据，列出 Top 技能和出现频次
3. 当用户要求"分析/搜索"某岗位时，说明你会触发系统自动搜索并提取最新数据
4. 回答简洁，每个技能要点一行，不要超过 500 字
5. 引用 JD 来源时标注公司名，增加可信度"""


class ChatAgent:
    def reply(self, user_message: str, context: str) -> tuple[str, dict]:
        prompt = f"{CHAT_SYSTEM_PROMPT}\n\n知识库上下文：\n{context}\n\n用户：{user_message}"
        msg = get_utility_llm().invoke(prompt)
        response = msg.content.strip()
        usage = msg.response_metadata.get("token_usage", {})
        logger.debug(f"ChatAgent 回复: {len(response)} 字")
        return response, {"prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0)}
