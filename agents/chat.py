"""对话 Agent —— 理解+决策一体（轻量模型 deepseek-chat）"""
from agents.base import get_utility_llm
from core.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """你是求职助手，帮用户分析岗位技能需求。

## 回复协议
回复第一行用以下标记指定动作（只用于需要搜索/分析的场景，普通对话不写标记）：
- [SEARCH:关键词] — 需要从知识库检索数据来回答
- [ANALYZE:岗位名] — 需要分析搜索最新招聘市场
- 普通对话（问候/闲聊/能力说明）不写标记，直接回复

## 回答规则
1. 当上下文包含技能排名时，列出 Top 技能和出现频次
2. 当上下文包含 JD 片段时，引用来源（公司名）
3. 回答简洁，最多 500 字
4. 用户追问确认"好的/可以/帮我分析"时，参考上一轮的岗位名执行分析
"""


class ChatAgent:

    @staticmethod
    def parse(response: str) -> tuple[str, str]:
        """
        解析 ChatAgent 回复中的标记（检查全部行）。
        返回 (action, arg)，action 为 "search"/"analyze"/"chat"
        """
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("[SEARCH:") and line.endswith("]"):
                return "search", line[9:-1]
            if line.startswith("[ANALYZE:") and line.endswith("]"):
                return "analyze", line[10:-1]
        return "chat", ""

    def reply(self, user_message: str, context: str) -> tuple[str, dict]:
        prompt = f"{SYSTEM_PROMPT}\n\n{context}\n\n用户：{user_message}"
        msg = get_utility_llm().invoke(prompt)
        response = msg.content.strip()
        usage = msg.response_metadata.get("token_usage", {})
        logger.debug(f"ChatAgent 回复: {len(response)} 字")
        return response, {"prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0)}
