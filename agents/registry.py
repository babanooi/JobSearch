"""多 Agent 组件注册中心 """
from agents.search_agent import SearchAgent
from agents.extract_agent import ExtractAgent
from tools.search_tool import JobSearchTool
from tools.db_tool import DBTool


class Registry:
    def __init__(self):
        self.search_tool = JobSearchTool()
        self.db_tool = DBTool()
        self.search_agent = SearchAgent(search_tool=self.search_tool)
        self.extract_agent = ExtractAgent()


registry = Registry()
