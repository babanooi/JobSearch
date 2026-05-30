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
    # 短岗位名后缀 — ≤4字前缀 + 开发/工程师/岗位/实习
    r"^.{0,4}(开发|工程师|岗位|实习)$",
    # 含限定词的岗位名 — "Web前端开发"、"前后端开发"、"服务端开发"等
    r"(前端|后端|前后端|全栈|服务端|接口|代码|脚本|软件|智能体|爬虫|数据)(开发|研发)$",
    # 开发机/环境/服务 — "在线开发机"、"远程开发服务"等
    r"(在线|远程|云端|虚拟)(开发机|开发环境|开发服务|IDE)",
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
import json as _json
from pathlib import Path as _Path

_SKILL_CACHE = None  # (names: list[str], vectors: list)
_CACHE_FILE = _Path(__file__).resolve().parent.parent / "data" / "skill_embeddings.json"


def _load_skill_cache(embeddings):
    """懒加载已有技能名及其 embedding 向量。
    优先读本地缓存文件，无文件时才调 API 并持久化。"""
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

    # 尝试从本地文件加载
    if _CACHE_FILE.exists():
        try:
            cache_data = _json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            cached_names = cache_data.get("names", [])
            cached_vecs = cache_data.get("vectors", [])
            # 文件中的技能名和 DB 一致才复用
            if cached_names == names and len(cached_vecs) == len(names):
                _SKILL_CACHE = (cached_names, cached_vecs)
                logger.info(f"技能语义缓存命中: {len(names)} 个标准技能名（从文件加载）")
                return _SKILL_CACHE
            logger.info(f"技能名有变化（文件{len(cached_names)} vs DB{len(names)}），重新 embedding")
        except Exception as e:
            logger.warning(f"读取技能缓存文件失败: {e}")

    # 文件不存在或不一致，调 API 并持久化
    vectors = embeddings.embed_documents(names)
    _SKILL_CACHE = (names, vectors)
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(
            _json.dumps({"names": names, "vectors": vectors}, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"技能语义缓存就绪并持久化: {len(names)} 个标准技能名")
    except Exception as e:
        logger.warning(f"持久化技能缓存失败: {e}")

    return _SKILL_CACHE


def clear_skill_cache():
    """清除缓存（新技能入库后调用以刷新）"""
    global _SKILL_CACHE
    _SKILL_CACHE = None
    try:
        if _CACHE_FILE.exists():
            _CACHE_FILE.unlink()
            logger.info("技能缓存文件已清除")
    except Exception:
        pass


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
    """批量归一化：别名检查 + 一次 embed_documents 批量语义匹配"""
    if not skills:
        return skills

    import numpy as np

    # 1. 别名表优先
    result = []
    need_match = []  # (index, skill) 需要语义匹配的
    for i, s in enumerate(skills):
        lower = s.lower()
        if lower in ALIASES:
            result.append(ALIASES[lower])
        else:
            result.append(None)  # 占位
            need_match.append((i, s))

    if not need_match:
        return result

    # 2. 加载已有技能缓存
    names, vectors = _load_skill_cache(embeddings)
    if not names:
        for i, s in need_match:
            result[i] = s
        return result

    # 3. 批量嵌入所有新技能（一次 API 调用）
    new_skills = [s for _, s in need_match]
    try:
        new_vecs = embeddings.embed_documents(new_skills)
        # 转为 numpy 矩阵以便矢量计算
        existing_matrix = np.array(vectors)          # (M, D)
        new_matrix = np.array(new_vecs)              # (N, D)

        # 归一化
        existing_norm = existing_matrix / (np.linalg.norm(existing_matrix, axis=1, keepdims=True) + 1e-8)
        new_norm = new_matrix / (np.linalg.norm(new_matrix, axis=1, keepdims=True) + 1e-8)

        # 余弦相似度矩阵 (N, M)
        sim_matrix = np.dot(new_norm, existing_norm.T)

        # 每行找最高分
        best_indices = np.argmax(sim_matrix, axis=1)  # (N,)
        best_scores = np.max(sim_matrix, axis=1)      # (N,)

        for k, (i, s) in enumerate(need_match):
            if best_scores[k] >= 0.85:
                matched = names[best_indices[k]]
                logger.debug(f"技能归一化: '{s}' → '{matched}' (余弦相似度={best_scores[k]:.2f})")
                result[i] = matched
            else:
                result[i] = s
    except Exception as e:
        logger.warning(f"技能批量语义归一化失败: {e}")
        for i, s in need_match:
            if result[i] is None:
                result[i] = s

    return result


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
