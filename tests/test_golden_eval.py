"""v0.14 Golden Set 评测框架测试."""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "eval" / "golden_set_v1.json"


def test_golden_set_loads():
    """golden_set_v1.json 可以被加载"""
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) >= 3


def test_golden_set_has_required_fields():
    """每个 case 有必需字段"""
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    required = ["case_id", "job_name", "jd_texts", "resume_text",
                "gold_job_profile", "gold_candidate_profile", "gold_fit"]
    for case in data:
        for field in required:
            assert field in case, f"{case.get('case_id')} missing {field}"


def test_golden_set_gold_profile_fields():
    """gold_job_profile 有关键字段"""
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for case in data:
        jp = case["gold_job_profile"]
        assert "must_have_capabilities" in jp
        assert isinstance(jp["must_have_capabilities"], list)


def test_evaluate_case_scoring():
    """评测函数能在 mock 输出上计算分数"""
    from eval.run_golden_eval import _evaluate_case
    case = {
        "gold_job_profile": {"must_have_capabilities": ["Python", "FastAPI", "MySQL"]},
        "gold_candidate_profile": {"skill_keywords": ["Python", "FastAPI"], "project_keywords": ["Web平台"], "achievement_keywords": []},
        "gold_fit": {"overall_fit_level": "strong", "expected_strengths": ["技能匹配"], "expected_gaps": [], "expected_learning_keywords": []},
    }
    job_profile = {"must_have_capabilities": ["Python", "FastAPI", "Docker"], "responsibilities": []}
    cand_profile = {"skill_stack": [{"skill": "Python"}], "projects": [{"description": "Web平台"}], "achievements": []}
    fit_report = {"overall_fit_level": "strong", "strengths": ["技能匹配"], "gaps": [], "learning_plan": []}

    result = _evaluate_case(case, job_profile, cand_profile, fit_report)
    assert "passed" in result
    assert "score" in result
    assert "job_profile_score" in result
    assert "candidate_profile_score" in result
    assert "hallucination_flags" in result
    assert result["fit_level_match"] is True


def test_evaluate_case_hallucination_detection():
    """系统输出多出标准答案没有的关键词应被标记"""
    from eval.run_golden_eval import _evaluate_case
    case = {
        "gold_job_profile": {"must_have_capabilities": ["Python"]},
        "gold_candidate_profile": {"skill_keywords": [], "project_keywords": [], "achievement_keywords": []},
        "gold_fit": {"overall_fit_level": "weak", "expected_strengths": [], "expected_gaps": [], "expected_learning_keywords": []},
    }
    job_profile = {"must_have_capabilities": ["Python", "QuantumComputing"], "responsibilities": []}
    cand_profile = {"skill_stack": [], "projects": [], "achievements": []}
    fit_report = {"overall_fit_level": "weak", "strengths": [], "gaps": [], "learning_plan": []}

    result = _evaluate_case(case, job_profile, cand_profile, fit_report)
    assert len(result["hallucination_flags"]) > 0
    assert "quantumcomputing" in result["hallucination_flags"][0].lower()


def test_run_golden_eval_limit():
    """--limit 1 只跑 1 个 case"""
    from eval.run_golden_eval import run_golden_eval
    report = run_golden_eval(limit=1)
    assert report["summary"]["total_cases"] == 1
    assert len(report["cases"]) == 1


def test_run_golden_eval_output_structure():
    """输出结构包含 summary 和 cases"""
    from eval.run_golden_eval import run_golden_eval
    report = run_golden_eval(limit=2)
    assert "summary" in report
    assert "cases" in report
    summary = report["summary"]
    assert "total_cases" in summary
    assert "pass_rate" in summary
    assert "avg_score" in summary


def test_run_golden_eval_no_write_to_data():
    """不会写入 data/ 目录"""
    from eval.run_golden_eval import run_golden_eval
    report = run_golden_eval(limit=1, output="/tmp/test_golden_eval_output.json")
    assert not any(Path("data/").rglob("golden_eval*"))


def test_keyword_hit_rate():
    """关键词命中率计算"""
    from eval.run_golden_eval import _keyword_hit_rate
    gold = ["Python", "FastAPI", "MySQL", "Redis"]
    actual = ["Python", "FastAPI", "Docker"]
    rate, missed = _keyword_hit_rate(gold, actual)
    assert rate == 0.5
    assert "MySQL" in missed
    assert "Redis" in missed
