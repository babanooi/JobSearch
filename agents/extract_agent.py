from agents.base_agent import BaseAgent
from langchain.prompts import PromptTemplate
from utils.logger import get_logger

logger = get_logger(__name__)

class ExtractAgent(BaseAgent):
    def __init__(self):
        super().__init__()   #继承父类的__init__

        self.prompt = PromptTemplate.from_template("""
        你是专业的招聘技能提取专家。
        请从下面的招聘文本中，**只提取技术技能关键词**。

        规则：
        1. 只提取有关该岗位的技术名词，如 Python, FastAPI, MySQL, Docker
        2. 不要句子，不要解释
        3. 用逗号分隔输出,**【绝对不要去重！】**
        4. 只输出技能，不要其他任何内容,同一个技能在不同招聘中出现多少次，就必须在结果中出现多少次
        5. 【重要】**不要去重！不要去重！** 你要想象自己在做统计，每出现一次就记录一次，不要帮用户合并
        招聘文本：
        {content}
        """)

    def run(self,content:str) ->list[str]:
        logger.debug("ExtractAgent 开始提取技能...")
        chain = self.prompt | self.llm
        result = chain.invoke({"content":content}).content.strip()

        skill_list = [ text.strip() for text in result.split(",") if text.strip() ]
        logger.debug(f"ExtractAgent 提取完成: {len(skill_list)} 个技能")
        return skill_list