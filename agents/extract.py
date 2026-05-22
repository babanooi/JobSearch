from agents.base import BaseAgent
from langchain_core.prompts import PromptTemplate
from core.logger import get_logger

logger = get_logger(__name__)


class ExtractAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.prompt = PromptTemplate.from_template("""
        你是专业的招聘技能提取专家。
        请从下面的招聘文本中，**只提取技术技能关键词**。

        规则：
        1. 只提取有关该岗位的技术名词，如 Python, FastAPI, MySQL, Docker
        2. 不要句子，不要解释
        3. 用逗号分隔输出，**【绝对不要去重！】**
        4. 同一个技能在不同招聘中出现多少次，就必须在结果中出现多少次
        5. 【重要】**不要去重！不要去重！** 统计时每出现一次就记录一次

        招聘文本：
        {content}
        """)

    def run(self, content: str) -> tuple[list[str], dict]:
        logger.debug("ExtractAgent 开始提取技能...")
        chain = self.prompt | self.llm
        msg = chain.invoke({"content": content})
        skill_list = [text.strip() for text in msg.content.strip().split(",") if text.strip()]
        usage = msg.response_metadata.get("token_usage", {})
        logger.debug(f"ExtractAgent 提取完成: {len(skill_list)} 个技能")
        return skill_list, {"prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0)}
