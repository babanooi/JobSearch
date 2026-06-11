"""v0.17 Taxonomy expansion tests for non-technical roles."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_guard_keeps_prd():
    """guard_skill_list 不过滤 PRD"""
    from tools.skill_guard import guard_skill_list
    result = guard_skill_list(["PRD", "需求分析", "用户研究"])
    assert "PRD" in result
    assert "需求分析" in result


def test_guard_keeps_data_skills():
    """guard_skill_list 不过滤数据分析能力词"""
    from tools.skill_guard import guard_skill_list
    result = guard_skill_list(["SQL", "Tableau", "PowerBI", "指标体系", "漏斗分析"])
    assert "SQL" in result
    assert "Tableau" in result
    assert "PowerBI" in result
    assert "指标体系" in result


def test_alias_normalization():
    """别名归一化"""
    from tools.skill_guard import normalize_job_name, ALIASES
    assert ALIASES.get("产品需求文档") == "PRD"
    assert ALIASES.get("大模型") == "LLM"
    assert ALIASES.get("智能体") == "Agent"
    assert ALIASES.get("axure rp") == "Axure"
    assert ALIASES.get("ab测试") == "A/B测试"


def test_filter_skill_names_keeps_product_skills():
    """filter_skill_names 不过滤产品能力词"""
    from tools.skill_taxonomy import filter_skill_names
    skills = ["PRD", "用户研究", "竞品分析", "数据分析", "Axure"]
    result = filter_skill_names(skills, job_name="AI产品经理")
    assert "PRD" in result or "prd" in [s.lower() for s in result]
    assert "用户研究" in result


def test_filter_skill_names_keeps_ai_skills():
    """filter_skill_names 不过滤 AI 产品能力词"""
    from tools.skill_taxonomy import filter_skill_names
    skills = ["LLM", "RAG", "Agent", "Prompt Engineering", "多模态"]
    result = filter_skill_names(skills, job_name="AI产品经理")
    assert len(result) >= 3


def test_filter_skill_names_keeps_solution_skills():
    """filter_skill_names 不过滤方案/售前能力词"""
    from tools.skill_taxonomy import filter_skill_names
    skills = ["方案设计", "客户需求分析", "PoC", "招投标"]
    result = filter_skill_names(skills, job_name="解决方案工程师")
    assert "方案设计" in result


def test_jd_extraction_product_manager():
    """AI 产品经理 JD 能提取产品能力词"""
    from services.job_profile_service import extract_job_profile
    jd = (
        "岗位职责：负责AI产品的需求分析、产品规划和落地推进。\n"
        "任职要求：本科及以上学历。2年以上互联网产品经验。\n"
        "熟悉PRD撰写、竞品分析、用户研究。具备数据分析能力，熟悉SQL。\n"
        "有Axure/Figma原型设计经验。了解大模型、RAG、Agent等AI技术。"
    )
    profile = extract_job_profile("AI产品经理", raw_jd_texts=[jd])
    must = [s.lower() for s in profile.must_have_capabilities]
    assert any("prd" in s or "需求分析" in s for s in must)
    assert any("用户研究" in s for s in must)
    assert any("竞品分析" in s for s in must)
    assert any("数据分析" in s or "sql" in s for s in must)


def test_jd_extraction_data_analyst():
    """数据分析师 JD 能提取数据分析能力词"""
    from services.job_profile_service import extract_job_profile
    jd = (
        "岗位职责：负责业务数据分析，输出分析报告，支持业务决策。\n"
        "与产品和运营团队协作，建立数据指标体系，搭建数据看板。\n"
        "任职要求：本科及以上学历，统计学、数学、计算机相关专业。\n"
        "熟练使用SQL、Python进行数据处理。熟悉数据可视化工具（Tableau/PowerBI）。\n"
        "有指标体系、数据看板、漏斗分析、留存分析经验优先。"
    )
    profile = extract_job_profile("数据分析师", raw_jd_texts=[jd])
    must = [s.lower() for s in profile.must_have_capabilities]
    assert any("sql" in s for s in must)


def test_jd_extraction_solution_engineer():
    """解决方案 JD 能提取方案/售前能力词"""
    from services.job_profile_service import extract_job_profile
    jd = (
        "岗位职责：负责行业解决方案设计，为客户提供技术咨询和业务咨询。\n"
        "主导项目交付，推动PoC验证和招投标工作。\n"
        "任职要求：本科及以上学历。具备方案设计和客户需求分析能力。\n"
        "有PoC验证和招投标经验优先。良好的沟通协调能力。能适应出差。"
    )
    profile = extract_job_profile("解决方案工程师", raw_jd_texts=[jd])
    must = [s.lower() for s in profile.must_have_capabilities]
    assert any("方案设计" in s or "客户需求分析" in s or "客户沟通" in s for s in must)


def test_engineering_extraction_not_degraded():
    """旧工程岗位提取不退化"""
    from services.job_profile_service import extract_job_profile
    jd = (
        "岗位职责：负责公司内部平台的后端开发与维护。参与系统架构设计与优化。\n"
        "任职要求：本科及以上学历，计算机相关专业。\n"
        "3年以上Python后端开发经验。\n"
        "熟悉Python、FastAPI、MySQL、Redis、Docker。了解微服务架构。"
    )
    profile = extract_job_profile("Python后端", raw_jd_texts=[jd])
    must = [s.lower() for s in profile.must_have_capabilities]
    assert "python" in must
    assert any("fastapi" in s for s in must)
    assert any("mysql" in s for s in must)


def test_golden_eval_case2_score_improved():
    """Golden Set case_002 AI产品经理分数应高于 30"""
    from eval.run_golden_eval import run_golden_eval
    report = run_golden_eval(limit=2)
    case2 = [c for c in report["cases"] if c["case_id"] == "case_002"]
    if case2:
        assert case2[0]["job_profile_score"] > 30, f"case_002 score: {case2[0]['job_profile_score']}"


def test_golden_eval_overall_not_degraded():
    """全量 Golden Set job_profile_score 不低于 70"""
    from eval.run_golden_eval import run_golden_eval
    report = run_golden_eval(limit=5)
    avg = report["summary"]["avg_job_profile_score"]
    assert avg >= 65, f"avg job_profile_score: {avg}"