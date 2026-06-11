"""LLM 输出校验 —— 过滤异常技能关键词，归一化别名 + 岗位名归一化 + 技能语义归一化"""
import re
import json as _json
from pathlib import Path as _Path
from core.logger import get_logger
from tools.skill_taxonomy import assess_skill_quality

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
    # 含限定词的岗位名 — "Web前端开发"、"前后端开发"等
    r"(前端|后端|前后端|全栈|服务端|接口|代码|脚本|软件|智能体|爬虫|数据)(开发|研发)$",
    # 开发机/环境/服务 — "在线开发机"、"远程开发服务"等
    r"(在线|远程|云端|虚拟)(开发机|开发环境|开发服务|IDE)",
]

ALIASES = {
    # 工程技术
    "react.js": "React", "reactjs": "React",
    "vue.js": "Vue", "vuejs": "Vue",
    "node.js": "Node.js", "nodejs": "Node.js",
    "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "golang": "Go", "go语言": "Go",
    # 产品
    "产品需求文档": "PRD", "需求文档": "PRD", "prd": "PRD",
    "用户调研": "用户研究", "竞品调研": "竞品分析",
    "axure rp": "Axure", "axure": "Axure",
    "figma": "Figma", "figma设计": "Figma",
    "墨刀": "墨刀", "modao": "墨刀",
    "原型": "原型设计",
    "ab测试": "A/B测试", "ab test": "A/B测试",
    "数据埋点": "数据埋点", "埋点分析": "数据埋点",
    # AI
    "大语言模型": "LLM", "大模型": "LLM",
    "检索增强生成": "RAG", "检索增强": "RAG",
    "智能体": "Agent", "ai agent": "Agent", "aiagent": "Agent",
    "prompt engineering": "Prompt Engineering", "提示词工程": "Prompt Engineering",
    "多模态大模型": "多模态",
    # 数据分析
    "power bi": "PowerBI", "powerbi": "PowerBI",
    "business intelligence": "BI", "bi工具": "BI",
    # 方案/售前
    "poc": "PoC", "poc验证": "PoC",
    "招投标": "招投标", "投标": "招投标",
}

# ═══ 非技术岗位能力词白名单 ═══
# 这些词不会被 guard_skill_list 过滤，允许进入 must_have/nice_to_have
CAPABILITY_WHITELIST = {
    # 产品能力
    "PRD", "需求分析", "用户研究", "竞品分析", "产品设计", "原型设计",
    "Axure", "Figma", "墨刀", "用户画像", "业务流程", "产品规划",
    "数据埋点", "A/B测试", "用户增长", "Roadmap", "MVP",
    # 数据分析
    "SQL", "Excel", "Tableau", "PowerBI", "BI",
    "指标体系", "数据看板", "漏斗分析", "留存分析", "转化率",
    "用户行为分析", "统计分析", "可视化",
    # AI 产品/应用
    "LLM", "RAG", "Prompt Engineering", "Agent", "多模态",
    "知识库", "向量数据库", "模型评估", "AI应用落地", "AI产品设计",
    "智能客服", "推荐系统", "搜索推荐", "AIGC",
    # 解决方案/售前
    "方案设计", "客户需求分析", "项目交付", "PoC", "招投标",
    "技术方案", "需求调研", "客户沟通", "业务咨询", "行业解决方案",
    # 项目管理/协作
    "项目管理", "跨部门协作", "需求管理", "进度管理", "风险管理",
    "Scrum", "Jira", "沟通协调", "文档能力",
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

    if _CACHE_FILE.exists():
        try:
            cache_data = _json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            cached_names = cache_data.get("names", [])
            cached_vecs = cache_data.get("vectors", [])
            if cached_names == names and len(cached_vecs) == len(names):
                _SKILL_CACHE = (cached_names, cached_vecs)
                logger.info(f"技能语义缓存命中: {len(names)} 个标准技能名（从文件加载）")
                return _SKILL_CACHE
            logger.info(f"技能名有变化（文件{len(cached_names)} vs DB{len(names)}），重新 embedding")
        except Exception as e:
            logger.warning(f"读取技能缓存文件失败: {e}")

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

    result = []
    need_match = []
    for i, s in enumerate(skills):
        lower = s.lower()
        if lower in ALIASES:
            result.append(ALIASES[lower])
        else:
            result.append(None)
            need_match.append((i, s))

    if not need_match:
        return result

    names, vectors = _load_skill_cache(embeddings)
    if not names:
        for i, s in need_match:
            result[i] = s
        return result

    new_skills = [s for _, s in need_match]
    try:
        new_vecs = embeddings.embed_documents(new_skills)
        existing_matrix = np.array(vectors)
        new_matrix = np.array(new_vecs)

        existing_norm = existing_matrix / (np.linalg.norm(existing_matrix, axis=1, keepdims=True) + 1e-8)
        new_norm = new_matrix / (np.linalg.norm(new_matrix, axis=1, keepdims=True) + 1e-8)
        sim_matrix = np.dot(new_norm, existing_norm.T)

        best_indices = np.argmax(sim_matrix, axis=1)
        best_scores = np.max(sim_matrix, axis=1)

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
        if not isinstance(skill, str):
            rejected.append(str(skill))
            continue
        skill = skill.strip()
        if not skill:
            continue
        skill_lower = skill.lower()
        skill = ALIASES.get(skill_lower, skill)
        # 白名单内的能力词直接保留
        if skill in CAPABILITY_WHITELIST or skill_lower in {s.lower() for s in CAPABILITY_WHITELIST}:
            cleaned.append(skill)
            continue
        if any(re.search(p, skill) for p in BLOCK_PATTERNS):
            rejected.append(skill)
            continue
        meta = assess_skill_quality(skill)
        if not meta["accepted"]:
            rejected.append(skill)
            continue
        cleaned.append(skill)

    if rejected:
        logger.warning(f"skill_guard 过滤 {len(rejected)} 个异常: {rejected[:10]}")
    return cleaned
