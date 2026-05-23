from tavily import TavilyClient
from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)


class JobSearchTool:
    def __init__(self):
        self.client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        self.include_domains = ["zhipin.com"]

    def search_job_info(self, job_name: str) -> list[dict]:
        """返回结构化搜索结果，保留 URL/标题等元数据"""
        query = f"{job_name}最新招聘要求 核心技能 任职资格 岗位职责"
        logger.debug(f"Tavily 搜索: {job_name}")
        res = self.client.search(
            query=query, search_depth="basic",
            include_domains=self.include_domains, max_results=5,
        )
        items = []
        for item in res.get("results", []):
            items.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score", 0),
            })
        logger.debug(f"Tavily 返回 {len(items)} 条结果")
        return items
