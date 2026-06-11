"""v0.16 Job profile extraction enhancement tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SAMPLE_JD = (
    "岗位职责：\n"
    "负责公司内部平台的后端开发与维护。\n"
    "参与系统架构设计与优化。\n"
    "推动技术方案落地。\n\n"
    "任职要求：\n"
    "本科及以上学历，计算机相关专业。\n"
    "3年以上Python后端开发经验。\n"
    "熟悉Python、FastAPI、MySQL、Redis、Docker。\n"
    "了解微服务架构、RESTful API设计。\n\n"
    "加分项：\n"
    "熟悉Kubernetes、CI/CD、Prometheus。\n"
    "有大模型/RAG相关项目经验优先。"
)

INTERNSHIP_JD = (
    "岗位职责：参与公司Web前端项目开发。任职要求：本科在校生，计算机相关专业。熟悉JavaScript、Vue、HTML5、CSS3。"
)


def test_extract_responsibilities():
    """能从 JD 中提取岗位职责"""
    from services.job_profile_service import _extract_responsibilities
    result = _extract_responsibilities([SAMPLE_JD])
    assert len(result) >= 2
    assert any("后端开发" in r for r in result)


def test_extract_must_have_skills():
    """能从 JD 中提取必备技能"""
    from services.job_profile_service import _extract_must_have_skills
    result = _extract_must_have_skills([SAMPLE_JD])
    names = [s.lower() for s in result]
    assert "python" in names
    assert "fastapi" in names or "fastapi" in str(names)
    assert "mysql" in names


def test_must_vs_nice_to_have():
    """能区分 must_have 和 nice_to_have"""
    from services.job_profile_service import extract_job_profile
    profile = extract_job_profile("Python后端", raw_jd_texts=[SAMPLE_JD])
    must = [s.lower() for s in profile.must_have_capabilities]
    nice = [s.lower() for s in profile.nice_to_have_capabilities]
    assert "python" in must
    # kubernetes 应该在加分项
    assert "kubernetes" in nice or any("kubernetes" in n for n in nice)


def test_extract_education():
    """能提取本科/专业要求"""
    from services.job_profile_service import extract_job_profile
    profile = extract_job_profile("Python后端", raw_jd_texts=[SAMPLE_JD])
    assert profile.education_preference in ("本科", "硕士", "博士")
    assert "计算机" in profile.major_preference


def test_extract_experience():
    """能提取经验要求"""
    from services.job_profile_service import extract_job_profile
    profile = extract_job_profile("Python后端", raw_jd_texts=[SAMPLE_JD])
    assert profile.experience_requirement != "未明确"
    assert "3" in profile.experience_requirement or "年" in profile.experience_requirement


def test_infer_job_type_internship():
    """能识别实习岗位"""
    from services.job_profile_service import extract_job_profile
    profile = extract_job_profile("前端实习", raw_jd_texts=[INTERNSHIP_JD])
    assert profile.job_type == "实习"
    assert profile.target_audience == "在校生/应届生"


def test_no_evidence_no_fabrication():
    """无证据字段不编造"""
    from services.job_profile_service import extract_job_profile
    profile = extract_job_profile("某未知岗位", raw_jd_texts=["这是一段完全没有岗位信息的文本，不包含任何职责和要求。"])
    assert profile.education_preference in ("未明确", "")
    assert profile.experience_requirement in ("未明确", "")


def test_skill_synonym_normalization():
    """同义词归一化有效"""
    from services.job_profile_service import _normalize_skill
    assert _normalize_skill("React.js") == "React"
    assert _normalize_skill("Vue.js") == "Vue"
    assert _normalize_skill("k8s") == "Kubernetes"
    assert _normalize_skill("K8S") == "Kubernetes"
    assert _normalize_skill("golang") == "Go"


def test_golden_eval_script_runs():
    """Golden Set 评测脚本仍可运行"""
    from eval.run_golden_eval import run_golden_eval
    report = run_golden_eval(limit=1)
    assert report["summary"]["total_cases"] == 1
    assert "avg_score" in report["summary"]


def test_jd_quality_filter_still_works():
    """旧 JD 质量过滤不被破坏"""
    from services.jd_quality_service import judge_jd_quality
    result = judge_jd_quality("招人", "")
    assert result["is_valid"] is False
