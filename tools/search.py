import json
import urllib.request
from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)

ANYSEARCH_URL = "https://api.anysearch.com/v1/search"


class JobSearchTool:
    def __init__(self):
        self.api_key = settings.ANYSEARCH_API_KEY

    def search_job_info(self, job_name: str) -> list[dict]:
        """返回结构化搜索结果，保留 URL/标题等元数据"""
        query = f"{job_name}最新招聘要求 核心技能 任职资格 岗位职责 site:zhipin.com"
        logger.debug(f"AnySearch 搜索: {job_name}")

        try:
            body = json.dumps({"query": query, "num": 5}).encode()
            req = urllib.request.Request(
                ANYSEARCH_URL,
                data=body,
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
            )
            resp = urllib.request.urlopen(req, timeout=15)
            raw = json.loads(resp.read().decode())
        except Exception as e:
            logger.error(f"AnySearch 搜索失败: {e}")
            return []

        items = []
        for item in raw.get("data", {}).get("results", []):
            items.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": 0,
            })
        logger.debug(f"AnySearch 返回 {len(items)} 条结果")
        return items
