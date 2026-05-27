"""LLM 输出校验 —— 过滤异常技能关键词，归一化别名 + 岗位名归一化 + 技能语义归一化"""
import re
from core.logger import get_logger

logger = get_logger(__name__)

# ═══ 技能过滤 ═══
BLOCK_PATTERNS = [
    r"^[0-9]+$",
    r"^.{30,}$",
    r"[，。；！？、]",
    r"^(和|的|及|与|或|等)$",
    r"^(招聘|岗位|要求|职责|任职)$",
    r"^.{0,4}(开发|工程师|岗位|实习)$",  # 短岗位名后缀，避免"后端开发"误入库
]

ALIASES = {
    "react.js": "React", "reactjs": "React",
    "node.js": "Node.js", "nodejs": "Node.js",
    "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "golang": "Go", "go语言": "Go",
}

# ═══ 岗位名归一化 ═══
JOB_ALIASES = {
    "python后端": "Python后端",
    "python后端工程师": "Python后端",
    "python后端开发": "Python后端",
    "python后端 招聘 技能": "Python后端",
    "python后端 招聘 技能要求": "Python后端",
    "ython后端": "Python后端",
    "入式开发工程师": "嵌入式开发工程师",
    "嵌入式开发": "嵌入式开发工程师",
    "agent应用开发": "Agent应用开发",
    "aiagent应用开发工程师": "Agent应用开发",
    "ai agent应用开发": "Agent应用开发",
    "java开发": "Java开发",
    "大模型工程师": "大模型开发",
    "大模型开发工程师": "大模型开发",
    "java后端": "Java开发",
    "java后端工程师": "Java开发",
    "java后端开发": "Java开发",
    "样本测试岗": "测试岗",
    "python测试岗": "测试岗",
    "python测试工程师": "测试岗",
    "样本测试": "测试岗",
}


def normalize_job_name(raw_name: str) -> str:
    """岗位名归一化：查别名表 + strip + 首字母大写"""
    name = raw_name.strip()
    if not name:
        return name
    key = name.lower()
    if key in JOB_ALIASES:
        return JOB_ALIASES[key]
    return name[0].upper() + name[1:] if len(name) > 1 else name.upper()


# ═══ 技能语义归一化 ═══
_SKILL_CACHE = None  # (names: list[str], vectors: list)


def _load_skill_cache(embeddings):
    """懒加载已有技能名及其 embedding 向量（缓存在内存中）"""
    global _SKILL_CACHE
    if _SKILL_CACHE is not None:
        return _SKILL_CACHE

    from models.database import SessionLocal
    from sqlalchemy import text
    with SessionLocal() as s:
        rows = s.execute(text("SELECT DISTINCT skill_name FROM job_skills")).fetchall()
        names = [r[0] for r in rows]

    if not names:
        _SKILL_CACHE = ([], [])
        return _SKILL_CACHE

    vectors = embeddings.embed_documents(names)
    _SKILL_CACHE = (names, vectors)
    logger.info(f"技能语义归一化缓存就绪: {len(names)} 个标准技能名")
    return _SKILL_CACHE


def clear_skill_cache():
    """清除缓存（新技能入库后调用以刷新）"""
    global _SKILL_CACHE
    _SKILL_CACHE = None


def normalize_skill_name(skill: str, embeddings) -> str:
    """语义匹配已有技能库，相似度 ≥ 0.85 则标准化为已有名"""
    # 1. 硬别名表优先
    lower = skill.lower()
    if lower in ALIASES:
        return ALIASES[lower]

    # 2. 语义匹配
    try:
        import numpy as np
        names, vectors = _load_skill_cache(embeddings)
        if not names:
            return skill

        skill_vec = embeddings.embed_query(skill)
        best_score = 0.0
        best_name = skill
        for name, vec in zip(names, vectors):
            cos = float(np.dot(skill_vec, vec) / (np.linalg.norm(skill_vec) * np.linalg.norm(vec) + 1e-8))
            if cos > best_score:
                best_score = cos
                best_name = name

        if best_score >= 0.85:
            logger.debug(f"技能归一化: '{skill}' → '{best_name}' (余弦相似度={best_score:.2f})")
            return best_name
    except Exception as e:
        logger.warning(f"技能语义归一化失败: {e}")

    return skill


def normalize_skill_list(skills: list[str], embeddings) -> list[str]:
    """批量归一化技能列表：别名 + 语义匹配"""
    return [normalize_skill_name(s, embeddings) for s in skills]


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
