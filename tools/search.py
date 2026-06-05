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

    @staticmethod
    def _score_job_result(item: dict, job_name: str) -> int:
        text = " ".join([
            item.get("title", ""),
            item.get("content", ""),
            item.get("url", ""),
        ]).lower()
        score = 0
        if job_name.lower() in text:
            score += 2
        if any(k in text for k in ["招聘", "职位", "岗位", "任职", "职责", "要求"]):
            score += 3
        if any(k in text for k in ["zhipin.com", "job_detail", "jobs"]):
            score += 2
        if any(k in text for k in ["培训", "课程", "百科", "是什么", "教程"]):
            score -= 2
        return score

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
            raw = data.get("data", {})
            results = raw.get("results", []) if isinstance(raw, dict) else raw
            for item in results:
                source_quality = self._score_job_result(item, job_name)
                if source_quality < 2:
                    continue
                items.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                    "score": item.get("score", 0),
                    "source_quality": source_quality,
                })
            logger.debug(f"AnySearch 返回 {len(items)} 条结果")
            return items
        except Exception as e:
            logger.error(f"AnySearch 搜索失败: {e}")
            return []
