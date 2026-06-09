"""技能差距分析单元测试 —— 使用 monkeypatch，不依赖真实 MySQL"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


# Mock 数据
MOCK_MARKET_SKILLS = [
    {"skill": "Python", "count": 30, "total_jds": 15},
    {"skill": "Django", "count": 22, "total_jds": 15},
    {"skill": "MySQL", "count": 18, "total_jds": 15},
    {"skill": "Redis", "count": 12, "total_jds": 15},
    {"skill": "Docker", "count": 10, "total_jds": 15},
    {"skill": "Linux", "count": 8, "total_jds": 15},
    {"skill": "Git", "count": 7, "total_jds": 15},
    {"skill": "RESTful API", "count": 6, "total_jds": 15},
    {"skill": "Nginx", "count": 5, "total_jds": 15},
    {"skill": "PostgreSQL", "count": 4, "total_jds": 15},
]


@pytest.fixture(autouse=True)
def mock_query_skill_rank(monkeypatch):
    """monkeypatch query_skill_rank 返回固定数据"""
    def mock_rank(job_name, top_n=10):
        return MOCK_MARKET_SKILLS[:top_n]
    monkeypatch.setattr("services.skill_gap.query_skill_rank", mock_rank)


def test_matched_skills():
    """用户技能能正确匹配市场技能"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", ["Python", "MySQL", "Git"])
    matched_names = [m["skill"] for m in result["matched_skills"]]
    assert "Python" in matched_names
    assert "MySQL" in matched_names
    assert "Git" in matched_names
    assert len(result["matched_skills"]) == 3


def test_missing_skills_sorted_by_count():
    """缺口技能按 count 降序排列"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", ["Python", "MySQL"])
    missing = result["missing_skills"]
    counts = [s["count"] for s in missing]
    assert counts == sorted(counts, reverse=True)
    # Django(count=22) 应该在 Redis(count=12) 前面
    django_idx = next(i for i, s in enumerate(missing) if s["skill"] == "Django")
    redis_idx = next(i for i, s in enumerate(missing) if s["skill"] == "Redis")
    assert django_idx < redis_idx


def test_empty_user_skills_coverage_zero():
    """空 user_skills 时覆盖率为 0，所有市场技能为 missing"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", [])
    assert result["coverage_ratio"] == 0.0
    assert len(result["matched_skills"]) == 0
    assert len(result["missing_skills"]) == len(MOCK_MARKET_SKILLS)


def test_full_coverage():
    """用户掌握所有市场技能时覆盖率 1.0"""
    from services.skill_gap import analyze_skill_gap
    all_skills = [s["skill"] for s in MOCK_MARKET_SKILLS]
    result = analyze_skill_gap("Python后端", all_skills)
    assert result["coverage_ratio"] == 1.0
    assert len(result["missing_skills"]) == 0
    assert len(result["priority_order"]) == 0


def test_no_market_data(monkeypatch):
    """无市场数据时返回合理结果"""
    monkeypatch.setattr("services.skill_gap.query_skill_rank", lambda *a, **kw: [])
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("不存在的岗位", ["Python"])
    assert result["market_skills"] == []
    assert result["coverage_ratio"] == 0.0
    assert "暂无" in result["summary"]


def test_priority_order_max_5():
    """学习优先级最多 5 个"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", ["Python"])
    assert len(result["priority_order"]) <= 5
    # 缺口 9 个，优先级应该取前 5
    assert len(result["priority_order"]) == 5


def test_alias_normalization():
    """别名归一化：k8s 应匹配 Kubernetes（如果在市场数据中）"""
    from services.skill_gap import analyze_skill_gap
    # 市场数据里没有 Kubernetes，但 k8s 应该被归一化
    result = analyze_skill_gap("Python后端", ["k8s", "python"])
    matched_names = [m["skill"] for m in result["matched_skills"]]
    # python 归一化后应该匹配 Python
    assert "Python" in matched_names


def test_case_insensitive_match():
    """大小写不敏感匹配"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", ["python", "MYSQL", "git"])
    matched_names = [m["skill"] for m in result["matched_skills"]]
    assert "Python" in matched_names
    assert "MySQL" in matched_names
    assert "Git" in matched_names


def test_summary_contains_coverage():
    """摘要包含覆盖率信息"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", ["Python", "MySQL"])
    assert "覆盖率" in result["summary"]
    assert "建议优先学习" in result["summary"]


def test_user_skills_none():
    """user_skills=None 时等价于空列表，覆盖率为 0"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", None)
    assert result["coverage_ratio"] == 0.0
    assert len(result["matched_skills"]) == 0
    assert len(result["missing_skills"]) == len(MOCK_MARKET_SKILLS)


def test_top_n_boundary():
    """top_n=1 只返回 1 个市场技能"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", ["Python", "Django", "MySQL"], top_n=1)
    assert len(result["market_skills"]) == 1
    assert result["market_skills"][0]["skill"] == "Python"
    assert result["coverage_ratio"] == 1.0  # 1/1 匹配


def test_job_name_stripped():
    """岗位名前后空格应被去除"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("  Python后端  ", ["Python"])
    assert result["job_name"] == "Python后端"


def test_matched_skills_are_objects():
    """matched_skills 返回对象列表，包含 count 和 total_jds"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", ["Python", "MySQL"])
    for item in result["matched_skills"]:
        assert isinstance(item, dict)
        assert "skill" in item
        assert "count" in item
        assert "total_jds" in item


def test_user_skills_with_none_and_empty():
    """user_skills 包含 None、空字符串、重复技能时不崩溃"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", ["Python", None, "", "python", "Python", None])
    # Python 应该匹配一次（去重后）
    assert "Python" in [m["skill"] for m in result["matched_skills"]]
    assert result["coverage_ratio"] > 0


def test_user_skills_all_garbage():
    """user_skills 全是无效输入时不崩溃"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", [None, "", None, 123, True])
    assert result["coverage_ratio"] == 0.0
    assert len(result["matched_skills"]) == 0


def test_service_layer_top_n_negative():
    """服务层 top_n=-1 应被限制为 1"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", ["Python"], top_n=-1)
    assert len(result["market_skills"]) == 1


def test_service_layer_top_n_over_50():
    """服务层 top_n=100 应被限制为 50"""
    from services.skill_gap import analyze_skill_gap
    result = analyze_skill_gap("Python后端", ["Python"], top_n=100)
    assert len(result["market_skills"]) <= 50


def test_filter_market_skills_filters_broad_terms():
    """filter_market_skills 会过滤掉泛词"""
    from services.skill_gap import filter_market_skills
    raw = [
        {"skill": "Python", "count": 30, "total_jds": 15},
        {"skill": "人工智能", "count": 10, "total_jds": 15},
        {"skill": "AI", "count": 8, "total_jds": 15},
        {"skill": "计算机科学", "count": 5, "total_jds": 15},
        {"skill": "Django", "count": 22, "total_jds": 15},
    ]
    result = filter_market_skills(raw, job_name="Python后端", top_n=10)
    names = [s["skill"] for s in result]
    assert "Python" in names
    assert "Django" in names
    assert "人工智能" not in names
    assert "AI" not in names
    assert "计算机科学" not in names


def test_filter_market_skills_returns_confidence_and_quality_reasons():
    """过滤后的结果应带 confidence 和 quality_reasons"""
    from services.skill_gap import filter_market_skills
    raw = [{"skill": "Python", "count": 30, "total_jds": 15}]
    result = filter_market_skills(raw, job_name="Python后端", top_n=10)
    assert len(result) == 1
    assert "confidence" in result[0]
    assert "quality_reasons" in result[0]


def test_estimate_market_confidence_high():
    """足够多的已知技能 → high"""
    from services.skill_gap import estimate_market_confidence
    market = [{"skill": f"s{i}"} for i in range(10)]
    result = estimate_market_confidence(market, raw_count=12, total_jds=10)
    assert result["confidence"] == "high"
    assert result["filtered_count"] == 2


def test_estimate_market_confidence_low_small_sample():
    """过滤后少于5个技能 → low"""
    from services.skill_gap import estimate_market_confidence
    market = [{"skill": f"s{i}"} for i in range(3)]
    result = estimate_market_confidence(market, raw_count=5, total_jds=2)
    assert result["confidence"] == "low"


# ── Skill Feedback API 测试 ──

def test_skill_feedback_reject():
    """reject 能保存"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    r = c.post('/skill_feedback', json={
        "user_id": 1, "job_name": "Python后端", "skill_name": "人工智能", "action": "reject"
    })
    assert r.status_code == 200
    assert r.json()["code"] == 200


def test_skill_feedback_important():
    """important 能保存"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    r = c.post('/skill_feedback', json={
        "user_id": 1, "job_name": "Python后端", "skill_name": "Docker", "action": "important"
    })
    assert r.status_code == 200
    assert r.json()["code"] == 200


def test_skill_feedback_no_duplicate():
    """重复反馈不会无限重复"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    # 确保 user 存在（FK 约束）
    c.get('/user?username=test_dup_user')
    r = c.get('/users')
    uid = r.json()['users'][-1]['id']
    # 使用唯一 skill_name + job_name 避免历史数据残留
    unique_skill = "UniqueSkill_Dedup_Test_2026"
    unique_job = "UniqueJob_Dedup_Test_2026"
    # 插入两次
    c.post('/skill_feedback', json={"user_id": uid, "job_name": unique_job, "skill_name": unique_skill, "action": "reject"})
    c.post('/skill_feedback', json={"user_id": uid, "job_name": unique_job, "skill_name": unique_skill, "action": "reject"})
    # summary 应该 reject_count=1
    r = c.get(f'/skill_feedback/summary?job_name={unique_job}&user_id={uid}')
    summary = r.json().get("summary", {})
    assert summary.get(unique_skill, {}).get("reject_count", 0) == 1


def test_skill_feedback_summary_returns_counts():
    """summary 返回 reject_count / important_count"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    c.post('/skill_feedback', json={"user_id": 1, "job_name": "测试岗位X", "skill_name": "AI", "action": "reject"})
    c.post('/skill_feedback', json={"user_id": 2, "job_name": "测试岗位X", "skill_name": "AI", "action": "reject"})
    c.post('/skill_feedback', json={"user_id": 3, "job_name": "测试岗位X", "skill_name": "AI", "action": "reject"})
    c.post('/skill_feedback', json={"user_id": 1, "job_name": "测试岗位X", "skill_name": "SQL", "action": "important"})
    r = c.get('/skill_feedback/summary?job_name=测试岗位X&user_id=1')
    summary = r.json().get("summary", {})
    assert summary["AI"]["reject_count"] == 3
    assert summary["AI"]["user_rejected"] is True
    assert summary["SQL"]["important_count"] == 1
    assert summary["SQL"]["user_marked_important"] is True
