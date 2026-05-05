from agents.base_agent import BaseAgent
from utils.logger import get_logger

logger = get_logger(__name__)


class SearchAgent(BaseAgent):
    """
      【搜索智能体】
      职责：仅负责联网获取岗位招聘原始文本
      单一职责原则：不做解析、不做提取、只做搜索
      """

    def __init__(self, search_tool):
        super().__init__()
        self.search_tool = search_tool

    def run(self, job_name: str) -> str:
        logger.debug(f"SearchAgent 开始搜索: {job_name}")
        raw_content = self.search_tool.search_job_info(job_name)
        logger.debug(f"SearchAgent 搜索完成，获取 {len(raw_content)} 条")
        return raw_content