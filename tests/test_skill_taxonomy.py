"""Skill taxonomy quality rules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.skill_taxonomy import assess_skill_quality, filter_skill_names, infer_job_family


def test_rejects_broad_ai_product_terms():
    bad = ["人工智能", "AI", "计算机科学", "软件工程", "信息技术", "IOT"]
    result = filter_skill_names(bad, job_name="ai产品经理")
    assert result == []


def test_keeps_actionable_product_skills():
    good = ["PRD", "需求分析", "竞品分析", "用户研究", "数据分析", "A/B测试", "SQL", "Figma"]
    result = filter_skill_names(good, job_name="ai产品经理")
    assert result == good


def test_rejects_job_title_like_words():
    bad = ["后端开发", "前端工程师", "智能体开发", "在线开发机服务"]
    result = filter_skill_names(bad, job_name="Python后端")
    assert result == []


def test_keeps_engineering_skills():
    good = ["Python", "FastAPI", "MySQL", "Redis", "Docker", "Kubernetes", "Linux"]
    result = filter_skill_names(good, job_name="Python后端")
    assert result == good


def test_job_family_inference():
    assert infer_job_family("ai产品经理") == "ai"
    assert infer_job_family("Python后端") == "backend"
    assert infer_job_family("测试工程师") == "test"


def test_confidence_metadata():
    meta = assess_skill_quality("需求分析", job_name="产品经理")
    assert meta["accepted"] is True
    assert meta["confidence"] == "high"


def test_enrich_skill_item_returns_quality_fields():
    """enrich_skill_item 应返回 confidence 和 quality_reasons"""
    from tools.skill_taxonomy import enrich_skill_item
    item = {"skill": "Python", "count": 30, "total_jds": 15}
    result = enrich_skill_item(item, job_name="Python后端")
    assert result is not None
    assert result["skill"] == "Python"
    assert "confidence" in result
    assert "quality_reasons" in result


def test_enrich_skill_item_rejects_broad_term():
    """enrich_skill_item 对泛词应返回 None"""
    from tools.skill_taxonomy import enrich_skill_item
    item = {"skill": "人工智能", "count": 10, "total_jds": 15}
    result = enrich_skill_item(item, job_name="ai产品经理")
    assert result is None
