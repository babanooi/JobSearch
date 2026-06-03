import os
import httpx
from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)


class JobSearchTool:
    def __init__(self):
        self.api_key = settings.ANYSEARCH_API_KEY or os.getenv("ANYSEARCH_API_KEY", "")
        self.base_url = "https://api.anysearch.com/v1"
        self.include_domains = ["zhipin.com"]

    def search_job_info(self, job_name: str) -> list[dict]:
        """返回结构化搜索结果，保留 URL/标题等元数据"""
        query = f"{job_name}最新招聘要求 核心技能 任职资格 岗位职责 site:zhipin.com"
        logger.debug(f"AnySearch 搜索: {job_name}")
        try:
            resp = httpx.post(
                f"{self.base_url}/search",
                json={"query": query, "limit": 10},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            items = []
            for item in data.get("data", []):
                items.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                    "score": item.get("score", 0),
                })
            logger.debug(f"AnySearch 返回 {len(items)} 条结果")
            return items
        except Exception as e:
            logger.error(f"AnySearch 搜索失败: {e}")
            return []
