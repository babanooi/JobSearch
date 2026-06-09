"""v0.13 Profile evaluation tests — unique fields to avoid DB residue."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _get_test_user_id():
    """获取或创建测试用户，返回 ID"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    c.get("/user?username=eval_test_user")
    r = c.get("/users")
    return r.json()["users"][-1]["id"]


def test_evaluation_model_can_create():
    """profile_evaluations 模型可创建"""
    from models.profile import ProfileEvaluation
    obj = ProfileEvaluation(user_id=1, target_type="job_profile", target_id=1, rating=4, is_correct=True)
    assert obj.rating == 4
    assert obj.is_correct is True


def test_post_evaluation_success():
    """POST /profile_evaluations 成功保存"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    uid = _get_test_user_id()
    r = c.post("/profile_evaluations", json={
        "user_id": uid,
        "target_type": "job_profile",
        "target_id": 9999,
        "rating": 4,
        "is_correct": True,
        "comment": "测试评估",
    })
    assert r.status_code == 200
    assert r.json()["code"] == 200
    assert r.json()["evaluation_id"] > 0


def test_evaluation_rating_out_of_range():
    """rating 超出 1-5 被拒绝"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    uid = _get_test_user_id()
    r = c.post("/profile_evaluations", json={
        "user_id": uid,
        "target_type": "job_profile",
        "target_id": 1,
        "rating": 6,
    })
    assert r.status_code == 422


def test_evaluation_invalid_target_type():
    """invalid target_type 被拒绝"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    uid = _get_test_user_id()
    r = c.post("/profile_evaluations", json={
        "user_id": uid,
        "target_type": "invalid_type",
        "target_id": 1,
    })
    assert r.status_code == 422


def test_evaluation_invalid_error_type():
    """invalid error_type 被拒绝"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    uid = _get_test_user_id()
    r = c.post("/profile_evaluations", json={
        "user_id": uid,
        "target_type": "job_profile",
        "target_id": 1,
        "error_type": "not_a_real_type",
    })
    assert r.status_code == 422


def test_list_evaluations_filter():
    """GET /profile_evaluations 可按 target_type 过滤"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    uid = _get_test_user_id()
    # 插入一条 job_profile 评估
    c.post("/profile_evaluations", json={
        "user_id": uid, "target_type": "job_profile", "target_id": 8888, "rating": 3,
    })
    # 查询
    r = c.get(f"/profile_evaluations?target_type=job_profile&user_id={uid}")
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert len(items) >= 1
    assert all(i["target_type"] == "job_profile" for i in items)


def test_evaluation_summary():
    """GET /profile_evaluations/summary 返回正确统计"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    uid = _get_test_user_id()
    # 插入几条评估
    for rating in [4, 5, 3]:
        c.post("/profile_evaluations", json={
            "user_id": uid, "target_type": "candidate_profile", "target_id": 7777,
            "rating": rating, "is_correct": rating >= 4, "error_type": "" if rating >= 4 else "weak_evidence",
        })
    r = c.get(f"/profile_evaluations/summary?target_type=candidate_profile&user_id={uid}")
    assert r.status_code == 200
    summary = r.json()
    assert summary["total_count"] >= 3
    assert summary["average_rating"] > 0
    assert summary["correct_rate"] >= 0


def test_summary_empty_returns_defaults():
    """无数据时 summary 返回合理默认值"""
    from services.profile_evaluation_service import summarize_evaluations
    result = summarize_evaluations(target_type="nonexistent_type_xyz")
    assert result["total_count"] == 0
    assert result["average_rating"] == 0
    assert result["correct_rate"] == 0
    assert result["error_type_counts"] == {}
    assert result["recent_items"] == []
