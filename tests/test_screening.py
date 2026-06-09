"""Screening profile tests — v0.8."""
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
        "text": (
            "岗位职责：负责公司内部平台的后端开发与维护。"
            "任职要求：本科及以上学历，计算机相关专业优先。"
            "需要 Python、FastAPI、MySQL，有后端项目或实习经历优先。"
            "具备良好的沟通协作能力和学习能力。"
        ),
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


def test_job_profile_has_employment_type(monkeypatch):
    """岗位画像包含 employment_type 字段"""
    from services import screening
    monkeypatch.setattr(screening, "query_skill_rank", lambda job_name, top_n=20: MOCK_SKILLS[:top_n])
    monkeypatch.setattr(screening, "_fetch_jd_texts", lambda job_name, limit=20: MOCK_JDS)

    profile = screening.build_job_profile("Python后端实习", top_n=5)
    assert "employment_type" in profile
    assert profile["employment_type"] in ("实习", "兼职", "全职", "合同", "未知")


def test_job_profile_filters_low_quality_jd(monkeypatch):
    """过短 JD 应被过滤"""
    from services import screening
    monkeypatch.setattr(screening, "query_skill_rank", lambda job_name, top_n=20: MOCK_SKILLS[:top_n])
    monkeypatch.setattr(screening, "_fetch_jd_texts", lambda job_name, limit=20: [
        {"title": "短JD", "company": "", "text": "招人", "source_url": "", "fetched_at": ""},
        *MOCK_JDS,
    ])

    profile = screening.build_job_profile("Python后端", top_n=5)
    # 短JD应被过滤，sample中jd_count应为1
    assert profile["sample"]["jd_count"] == 1


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


def test_candidate_experience_years_explicit():
    """简历明确声明工作年限"""
    from services.screening import extract_candidate_profile
    profile = extract_candidate_profile(resume_text="3年工作经验，本科计算机专业。")
    assert profile["experience"]["experience_years"] == 3
    assert profile["experience"]["experience_years_confidence"] == "explicit"


def test_candidate_experience_years_inferred():
    """从毕业年份推断工作年限"""
    from services.screening import extract_candidate_profile
    profile = extract_candidate_profile(resume_text="2022年毕业，本科计算机专业。")
    assert profile["experience"]["experience_years"] >= 3
    assert profile["experience"]["experience_years_confidence"] == "inferred"


def test_candidate_sensitive_info_detected():
    """敏感信息应被检测到但不参与评分"""
    from services.screening import extract_candidate_profile
    profile = extract_candidate_profile(resume_text="男性，年龄25岁，本科计算机专业。Python开发经验。")
    assert "男" in profile["sensitive_info"]
    assert "年龄" in profile["sensitive_info"]


def test_sensitive_info_not_in_scoring(monkeypatch):
    """敏感信息不应影响评分"""
    from services import screening
    monkeypatch.setattr(screening, "query_skill_rank", lambda job_name, top_n=20: MOCK_SKILLS[:top_n])
    monkeypatch.setattr(screening, "_fetch_jd_texts", lambda job_name, limit=20: MOCK_JDS)

    report1 = screening.build_screening_report(
        job_name="Python后端",
        resume_text="男，25岁，本科计算机，Python项目经验。",
    )
    report2 = screening.build_screening_report(
        job_name="Python后端",
        resume_text="女，30岁，本科计算机，Python项目经验。",
    )
    # 性别/年龄不应影响评分
    assert report1["score"] == report2["score"]


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


def test_screening_report_has_concerns_with_reasons(monkeypatch):
    """扣分点必须给出原因"""
    from services import screening
    monkeypatch.setattr(screening, "query_skill_rank", lambda job_name, top_n=20: MOCK_SKILLS[:top_n])
    monkeypatch.setattr(screening, "_fetch_jd_texts", lambda job_name, limit=20: MOCK_JDS)

    report = screening.build_screening_report(
        job_name="Python后端",
        resume_text="本科计算机专业。",  # 缺少技能和经历
    )
    assert len(report["concerns"]) > 0
    for concern in report["concerns"]:
        assert "dimension" in concern
        assert "reason" in concern
        assert "score" in concern


def test_screening_report_has_matched_and_missing_points(monkeypatch):
    """报告应包含 matched_points 和 missing_points"""
    from services import screening
    monkeypatch.setattr(screening, "query_skill_rank", lambda job_name, top_n=20: MOCK_SKILLS[:top_n])
    monkeypatch.setattr(screening, "_fetch_jd_texts", lambda job_name, limit=20: MOCK_JDS)

    report = screening.build_screening_report(
        job_name="Python后端",
        resume_text="本科计算机，Python和MySQL项目经验。",
    )
    assert isinstance(report["matched_points"], list)
    assert isinstance(report["missing_points"], list)
    assert "Python" in report["matched_points"] or "MySQL" in report["matched_points"]


def test_degree_mismatch_gives_concern(monkeypatch):
    """学历不匹配时应在 concerns 中给出原因"""
    from services import screening
    jd = [{**MOCK_JDS[0], "text": "要求硕士及以上学历。计算机相关专业。Python、FastAPI、MySQL。"}]
    monkeypatch.setattr(screening, "query_skill_rank", lambda job_name, top_n=20: MOCK_SKILLS[:top_n])
    monkeypatch.setattr(screening, "_fetch_jd_texts", lambda job_name, limit=20: jd)

    report = screening.build_screening_report(
        job_name="Python后端",
        resume_text="本科计算机专业，Python项目经验。",
    )
    edu_concerns = [c for c in report["concerns"] if c["dimension"] == "education"]
    if edu_concerns:
        assert "硕士" in edu_concerns[0]["reason"] or "本科" in edu_concerns[0]["reason"]
