"""Resume profile extraction tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.resume_profile import extract_profile_from_text, profile_to_skill_names


def test_extract_profile_by_rules_from_resume_text():
    text = """
    项目：JobLab 求职技能分析平台
    使用 Python、FastAPI 开发后端 API，使用 MySQL 存储 JD 和技能统计。
    通过 Docker 部署服务，并用 Redis 缓存任务状态。
    """
    profile = extract_profile_from_text(text, use_llm=False)
    names = {item["skill"].lower() for item in profile["skills"]}

    assert "python" in names
    assert "fastapi" in names
    assert "mysql" in names
    assert "docker" in names
    assert profile["parser"] == "rules"


def test_profile_to_skill_names_accepts_profile_dict_and_list():
    profile = {
        "skills": [
            {"skill": "Python", "level": "熟练"},
            {"skill": "FastAPI", "level": "使用过"},
        ]
    }
    assert profile_to_skill_names(profile) == ["Python", "FastAPI"]
    assert profile_to_skill_names(profile["skills"]) == ["Python", "FastAPI"]
