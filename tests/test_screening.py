"""Screening profile tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


MOCK_SKILLS = [
    {"skill": "Python", "count": 18, "total_jds": 20},
    {"skill": "FastAPI", "count": 14, "total_jds": 20},
    {"skill": "MySQL", "count": 12, "total_jds": 20},
    {"skill": "Docker", "count": 8, "total_jds": 20},
    {"skill": "Redis", "count": 6, "total_jds": 20},
]

MOCK_JDS = [
    {
        "title": "Python后端实习生",
        "company": "Example",
        "text": "本科及以上，计算机相关专业优先。需要 Python、FastAPI、MySQL，有后端项目或实习经历。具备沟通协作能力。",
        "source_url": "",
        "fetched_at": "2026-06-01T10:00:00",
    }
]


def test_build_job_profile(monkeypatch):
    from services import screening

    monkeypatch.setattr(screening, "query_skill_rank", lambda job_name, top_n=20: MOCK_SKILLS[:top_n])
    monkeypatch.setattr(screening, "_fetch_jd_texts", lambda job_name, limit=20: MOCK_JDS)

    profile = screening.build_job_profile("Python后端实习", top_n=5)

    assert profile["job_type"] == "实习"
    assert profile["target_audience"] == "在校生/应届生"
    assert "Python" in profile["must_have"]
    assert profile["education_requirements"][0]["degree"] == "本科"
    assert profile["major_requirements"][0]["major"] == "计算机"


def test_extract_candidate_profile_from_resume_text():
    from services.screening import extract_candidate_profile

    profile = extract_candidate_profile(
        resume_text="某大学本科计算机专业，2026届。项目：使用 Python、FastAPI 和 MySQL 开发求职分析平台，上线后提升分析效率 30%。",
        user_profile=[],
    )

    assert profile["education"]["degree"] == "本科"
    assert profile["education"]["major"] == "计算机"
    assert profile["experience"]["has_project"] is True
    assert any(item["skill"].lower() == "python" for item in profile["skills"])


def test_build_screening_report(monkeypatch):
    from services import screening

    monkeypatch.setattr(screening, "query_skill_rank", lambda job_name, top_n=20: MOCK_SKILLS[:top_n])
    monkeypatch.setattr(screening, "_fetch_jd_texts", lambda job_name, limit=20: MOCK_JDS)

    report = screening.build_screening_report(
        job_name="Python后端实习",
        resume_text="某大学本科计算机专业。项目：使用 Python、FastAPI 和 MySQL 开发后端 API，Docker 部署。",
        top_n=5,
    )

    assert report["score"] > 50
    assert report["pass_risk"] in {"low", "medium", "high"}
    matched = [s["name"] for s in report["matched_requirements"]["skills"]]
    assert "Python" in matched
    assert "blocking_issues" in report
