from agents.base import BaseAgent
from core.logger import get_logger

logger = get_logger(__name__)


class SearchAgent(BaseAgent):
    """仅负责联网获取岗位招聘原始文本，不做解析、不做提取"""

    def __init__(self, search_tool):
        super().__init__()
        self.search_tool = search_tool

    def run(self, job_name: str) -> list[dict]:
        logger.debug(f"SearchAgent 开始搜索: {job_name}")
        items = self.search_tool.search_job_info(job_name)
        logger.debug(f"SearchAgent 搜索完成，获取 {len(items)} 条结果")
        return items
