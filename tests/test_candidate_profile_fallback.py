"""v0.19 Candidate profile rule-based fallback tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SAMPLE_RESUME = (
    "张三，本科计算机科学与技术专业，2022年毕业。\n"
    "技能：Python、FastAPI、MySQL、Redis、Docker、Linux、Git。\n"
    "项目：开发了一个基于FastAPI的求职分析平台，使用MySQL存储数据，Redis缓存，Docker容器化部署，上线后日活500+。\n"
    "实习：在某科技公司担任后端开发实习生，参与内部管理系统开发。\n"
    "成果：优化数据库查询，性能提升30%。获得校级编程竞赛一等奖。\n"
    "自学Rust，GitHub开源项目贡献者。"
)

PRODUCT_RESUME = (
    "李四，硕士工商管理专业，2021年毕业。\n"
    "技能：PRD撰写、Axure、Figma、SQL、数据分析。\n"
    "项目：主导智能客服产品从0到1落地，上线后客户满意度提升20%。\n"
    "工作：在某互联网公司担任产品经理，负责用户增长方向。"
)

DATA_RESUME = (
    "赵六，本科数学专业，2023年毕业。\n"
    "技能：SQL、Python、Pandas、Excel。\n"
    "项目：电商用户行为分析，使用Pandas处理10万条用户数据，输出用户画像。\n"
    "成果：输出分析报告覆盖10万用户。"
)


def test_extract_education():
    """从简历提取本科/专业"""
    from services.candidate_profile_service import extract_candidate_profile
    profile = extract_candidate_profile(resume_text=SAMPLE_RESUME)
    assert profile.education_background["degree"] == "本科"
    assert "计算机" in profile.education_background["major"]


def test_extract_skills_rule_fallback():
    """规则兜底提取技能"""
    from services.candidate_profile_service import _extract_skills_from_text
    skills = _extract_skills_from_text(SAMPLE_RESUME)
    names = [s["skill"].lower() for s in skills]
    assert "python" in names
    assert "fastapi" in names or "fastapi" in str(names)
    assert "mysql" in names
    assert "redis" in names


def test_extract_projects():
    """提取项目经历"""
    from services.candidate_profile_service import _extract_projects
    projects = _extract_projects(SAMPLE_RESUME)
    assert len(projects) >= 1
    assert any("求职" in p["description"] or "FastAPI" in p["description"] for p in projects)


def test_extract_internships():
    """提取实习经历"""
    from services.candidate_profile_service import _extract_internships
    internships = _extract_internships(SAMPLE_RESUME)
    assert len(internships) >= 1
    assert any("科技公司" in i["description"] or "实习" in i["description"] or "后端" in i["description"] for i in internships)


def test_extract_work_experiences():
    """提取工作经历"""
    from services.candidate_profile_service import _extract_work_experiences
    work = _extract_work_experiences(PRODUCT_RESUME)
    assert len(work) >= 1
    assert any("产品经理" in w["description"] for w in work)


def test_extract_achievements():
    """提取量化成果"""
    from services.candidate_profile_service import _extract_achievements
    achievements = _extract_achievements(SAMPLE_RESUME)
    assert len(achievements) >= 1
    assert any("30" in a["description"] for a in achievements)


def test_extract_learning_signals():
    """提取学习能力信号"""
    from services.candidate_profile_service import _extract_learning_signals
    signals = _extract_learning_signals(SAMPLE_RESUME)
    assert "自主学习" in signals
    assert "开源参与" in signals


def test_sensitive_not_in_scoring():
    """敏感信息不参与评分"""
    from services.candidate_profile_service import extract_candidate_profile
    male = extract_candidate_profile(resume_text="男，25岁，本科，Python开发经验。")
    female = extract_candidate_profile(resume_text="女，30岁，本科，Python开发经验。")
    assert male.education_background == female.education_background


def test_fallback_returns_result():
    """没有 LLM 时 fallback 仍返回 CandidateProfileResult"""
    from services.candidate_profile_service import extract_candidate_profile
    from services.profile_schemas import CandidateProfileResult
    profile = extract_candidate_profile(resume_text="本科计算机，Python开发项目经验，提升30%性能。")
    assert isinstance(profile, CandidateProfileResult)
    assert len(profile.skill_stack) > 0 or len(profile.projects) > 0


def test_product_resume_extracts_prd():
    """产品简历提取 PRD/用户研究/竞品分析"""
    from services.candidate_profile_service import _extract_skills_from_text
    skills = _extract_skills_from_text(PRODUCT_RESUME)
    names = [s["skill"].lower() for s in skills]
    assert "prd" in names
    assert any("axure" in n for n in names)


def test_data_resume_extracts_sql():
    """数据分析简历提取 SQL/Pandas"""
    from services.candidate_profile_service import _extract_skills_from_text
    skills = _extract_skills_from_text(DATA_RESUME)
    names = [s["skill"].lower() for s in skills]
    assert "sql" in names
    assert "pandas" in names


def test_golden_eval_candidate_score_not_degraded():
    """Golden Set candidate_profile_score 不下降"""
    from eval.run_golden_eval import run_golden_eval
    report = run_golden_eval(limit=5)
    avg = report["summary"]["avg_candidate_profile_score"]
    assert avg >= 80, f"avg_candidate_profile_score: {avg}"
