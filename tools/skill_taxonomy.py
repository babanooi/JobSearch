"""Skill taxonomy and quality rules for market-skill extraction.

The goal is not to build a perfect dictionary. It is to reject broad,
non-actionable words before they enter skill ranking or skill-gap output.
"""
from __future__ import annotations

import re
from typing import Iterable


TECH_EXCEPTIONS = {
    "go", "c", "c++", "c#", "r", "sql", "nosql", "aiops",
    "rag", "llm", "nlp", "ocr", "cv", "mcp", "etl", "bi",
}

BROAD_TERMS = {
    "ai", "iot", "api", "net", "orm",
    "人工智能", "深度学习", "机器学习", "自然语言", "自然语言处理",
    "计算机科学", "软件工程", "信息技术", "大数据", "互联网",
    "前端", "后端", "服务端", "客户端", "全栈", "算法", "测试", "运维",
    "研发", "开发", "工程", "技术", "产品", "业务", "数据",
    "标注", "清洗", "维护", "编码", "调试", "重构", "辅导", "评测",
    "跨平台", "高性能", "高并发", "硬件设计", "软件代码",
    "多平台反汇编", "跨平台反汇编", "逆向分析", "漏洞挖掘", "利用",
}

ACTION_VERBS = {
    "清洗", "重构", "辅导", "测试", "评审", "评估", "审核", "调研",
    "排查", "部署", "迁移", "对接", "封装", "拆解", "利用",
}

KNOWN_SKILLS = {
    # Languages
    "python", "java", "javascript", "typescript", "go", "golang", "rust",
    "c", "c++", "c#", "php", "ruby", "scala", "kotlin", "swift",
    # Backend / web
    "django", "fastapi", "flask", "spring", "spring boot", "node.js",
    "express", "gin", "grpc", "restful api", "graphql", "微服务",
    # Data / infra
    "mysql", "postgresql", "redis", "mongodb", "elasticsearch", "kafka",
    "rabbitmq", "spark", "flink", "hadoop", "clickhouse", "airflow",
    "docker", "kubernetes", "k8s", "linux", "nginx", "git", "jenkins",
    "ci/cd", "terraform", "ansible",
    # AI / agent
    "pytorch", "tensorflow", "transformers", "langchain", "llamaindex",
    "rag", "prompt engineering", "agent", "mcp", "llm", "向量数据库",
    "embedding", "faiss", "milvus", "chromadb",
    # Product / design
    "prd", "axure", "figma", "jira", "confluence", "scrum", "敏捷",
    "用户研究", "需求分析", "竞品分析", "原型设计", "产品规划",
    "数据分析", "a/b测试", "ab测试", "埋点分析", "增长分析",
    # Test
    "自动化测试", "单元测试", "集成测试", "性能测试", "接口测试",
    "pytest", "selenium", "playwright", "jmeter",
}

JOB_FAMILY_KEYWORDS = {
    "backend": ("后端", "服务端", "java", "python", "go", "php"),
    "frontend": ("前端", "web", "vue", "react", "小程序"),
    "data": ("数据", "分析", "bi", "数仓", "算法"),
    "ai": ("ai", "大模型", "llm", "agent", "算法", "机器学习"),
    "product": ("产品", "pm", "产品经理"),
    "test": ("测试", "qa", "质量"),
    "embedded": ("嵌入式", "硬件", "单片机", "驱动"),
}

FAMILY_ALLOW = {
    "product": {
        "prd", "axure", "figma", "jira", "confluence", "scrum", "敏捷",
        "用户研究", "需求分析", "竞品分析", "原型设计", "产品规划",
        "数据分析", "a/b测试", "ab测试", "埋点分析", "增长分析",
        "sql", "prompt engineering", "rag", "llm", "agent",
    },
    "ai": {
        "pytorch", "tensorflow", "transformers", "langchain", "llamaindex",
        "rag", "prompt engineering", "agent", "mcp", "llm", "embedding",
        "向量数据库", "milvus", "faiss", "chromadb", "python",
    },
    "test": {
        "自动化测试", "单元测试", "集成测试", "性能测试", "接口测试",
        "pytest", "selenium", "playwright", "jmeter", "postman",
    },
}

JOB_TITLE_PATTERNS = [
    r"^.{0,4}(开发|工程师|岗位|实习)$",
    r"(前端|后端|前后端|全栈|服务端|接口|代码|脚本|软件|智能体|爬虫|数据)(开发|研发)$",
    r"(在线|远程|云端|虚拟)(开发机|开发环境|开发服务|IDE)",
]

ACTIONABLE_CN_PATTERNS = [
    r"(需求|竞品|用户|埋点|增长|数据|业务).{0,4}分析$",
    r"(原型|交互|产品|架构|系统).{0,4}设计$",
    r"(自动化|单元|集成|性能|接口).{0,2}测试$",
]


def infer_job_family(job_name: str = "") -> str:
    name = (job_name or "").lower()
    for family, keywords in JOB_FAMILY_KEYWORDS.items():
        if any(k.lower() in name for k in keywords):
            return family
    return "general"


def _looks_like_known_skill(skill: str, family: str) -> bool:
    lower = skill.lower()
    if lower in KNOWN_SKILLS:
        return True
    if lower in FAMILY_ALLOW.get(family, set()):
        return True
    if any(re.search(p, skill, re.I) for p in ACTIONABLE_CN_PATTERNS):
        return True
    # English technical terms usually have letters plus optional separators.
    if re.search(r"[A-Za-z]", skill) and re.fullmatch(r"[A-Za-z0-9+#./ -]{2,32}", skill):
        return True
    return False


def assess_skill_quality(skill: str, job_name: str = "") -> dict:
    """Return quality metadata for one candidate skill.

    confidence:
    - high: known/taxonomy skill
    - medium: plausible actionable skill
    - low: accepted only with weak evidence
    """
    if not isinstance(skill, str):
        return {"accepted": False, "confidence": "reject", "reasons": ["非字符串"], "category": "invalid"}

    s = skill.strip()
    if not s:
        return {"accepted": False, "confidence": "reject", "reasons": ["空技能"], "category": "invalid"}

    lower = s.lower()
    family = infer_job_family(job_name)

    if len(lower) <= 2 and lower not in TECH_EXCEPTIONS:
        return {"accepted": False, "confidence": "reject", "reasons": ["过短泛词"], "category": "short"}

    if lower in BROAD_TERMS or s in BROAD_TERMS:
        return {"accepted": False, "confidence": "reject", "reasons": ["过宽泛"], "category": "broad"}

    if s in ACTION_VERBS:
        return {"accepted": False, "confidence": "reject", "reasons": ["动作词"], "category": "verb"}

    if any(re.search(p, s) for p in JOB_TITLE_PATTERNS):
        return {"accepted": False, "confidence": "reject", "reasons": ["像岗位名"], "category": "job_title"}

    if any(ch in s for ch in "，。；！？、"):
        return {"accepted": False, "confidence": "reject", "reasons": ["包含标点"], "category": "punctuation"}

    if len(s) >= 30:
        return {"accepted": False, "confidence": "reject", "reasons": ["过长片段"], "category": "long_fragment"}

    if _looks_like_known_skill(s, family):
        return {"accepted": True, "confidence": "high", "reasons": ["taxonomy"], "category": family}

    # Let specific multi-character Chinese nouns pass with medium confidence.
    if 2 < len(s) <= 12 and not re.search(r"(熟悉|了解|掌握|负责|参与|完成|以上|以下)", s):
        return {"accepted": True, "confidence": "medium", "reasons": ["疑似专有技能"], "category": family}

    return {"accepted": False, "confidence": "reject", "reasons": ["不可执行"], "category": "weak"}


def filter_skill_names(skills: Iterable[str], job_name: str = "") -> list[str]:
    result = []
    for skill in skills:
        meta = assess_skill_quality(skill, job_name=job_name)
        if meta["accepted"]:
            result.append(skill.strip())
    return result


def enrich_skill_item(item: dict, job_name: str = "") -> dict | None:
    skill = item.get("skill") or item.get("skill_name") or ""
    meta = assess_skill_quality(skill, job_name=job_name)
    if not meta["accepted"]:
        return None
    enriched = dict(item)
    enriched["confidence"] = meta["confidence"]
    enriched["quality_reasons"] = meta["reasons"]
    return enriched
