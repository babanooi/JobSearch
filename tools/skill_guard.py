"""LLM 输出校验 —— 过滤异常技能关键词，归一化别名"""
import re
from core.logger import get_logger

logger = get_logger(__name__)

BLOCK_PATTERNS = [
    r"^[0-9]+$",
    r"^.{30,}$",
    r"[，。；！？、]",
    r"^(和|的|及|与|或|等)$",
    r"^(招聘|岗位|要求|职责|任职)$",
]

ALIASES = {
    "react.js": "React", "reactjs": "React",
    "node.js": "Node.js", "nodejs": "Node.js",
    "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "golang": "Go", "go语言": "Go",
}


def guard_skill_list(raw_skills: list[str]) -> list[str]:
    cleaned = []
    rejected = []
    for skill in raw_skills:
        skill = skill.strip()
        if not skill:
            continue
        if any(re.search(p, skill) for p in BLOCK_PATTERNS):
            rejected.append(skill)
            continue
        skill_lower = skill.lower()
        skill = ALIASES.get(skill_lower, skill)
        cleaned.append(skill)

    if rejected:
        logger.warning(f"skill_guard 过滤 {len(rejected)} 个异常: {rejected[:10]}")
    return cleaned
