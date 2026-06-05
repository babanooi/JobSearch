from agents.base import BaseAgent
from langchain_core.prompts import PromptTemplate
from core.logger import get_logger

logger = get_logger(__name__)


class ExtractAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.prompt = PromptTemplate.from_template("""
        你是专业的招聘技能提取专家。
        目标岗位：{job_name}

        请从下面的招聘文本中，**只提取可执行、可学习、可在简历中呈现的硬技能关键词**。

        规则：
        1. 保留具体技能：编程语言、框架、库、数据库、工具、协议、平台、测试方法、产品工具、分析方法。
        2. 删除泛领域词：AI、人工智能、软件工程、计算机科学、信息技术、前端、后端、算法、测试、运维。
        3. 删除岗位名、职责动词、行业大类、公司名、课程名、完整句子。
        4. 如果目标岗位是产品经理，可保留 PRD、Axure、Figma、需求分析、竞品分析、用户研究、数据分析、A/B测试、SQL。
        5. 用逗号分隔输出，不要解释。
        6. 不要去重。同一个技能在不同招聘中出现多少次，就在结果中出现多少次。

        招聘文本：
        {content}
        """)

    def run(self, content: str, job_name: str = "") -> tuple[list[str], dict]:
        logger.debug("ExtractAgent 开始提取技能...")
        chain = self.prompt | self.llm
        msg = chain.invoke({"content": content, "job_name": job_name or "未知岗位"})
        skill_list = [text.strip() for text in msg.content.strip().split(",") if text.strip()]
        usage = msg.response_metadata.get("token_usage", {})
        logger.debug(f"ExtractAgent 提取完成: {len(skill_list)} 个技能")
        return skill_list, {"prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0)}
