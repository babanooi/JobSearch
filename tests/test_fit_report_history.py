"""v0.22 Fit report history tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_USER_ID = 0


def _ensure_test_user():
    """确保测试用户存在，返回 user_id"""
    global TEST_USER_ID
    if TEST_USER_ID:
        return TEST_USER_ID
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    r = c.get("/user?username=test_history_user")
    TEST_USER_ID = r.json().get("user_id", 1)
    return TEST_USER_ID


_test_report_ids = []  # (report_id, job_profile_id, candidate_profile_id)


def _create_test_report():
    """Helper: 创建一条测试报告（含关联 job_profile 和 candidate_profile）"""
    uid = _ensure_test_user()
    from models.database import SessionLocal
    from models.profile import FitAnalysisReport, JobProfile, CandidateProfile
    with SessionLocal() as session:
        jp = JobProfile(job_name="测试岗位", confidence="medium")
        session.add(jp)
        session.flush()
        cp = CandidateProfile(user_id=uid, confidence="medium")
        session.add(cp)
        session.flush()
        obj = FitAnalysisReport(
            user_id=uid,
            job_profile_id=jp.id,
            candidate_profile_id=cp.id,
            overall_fit_level="moderate",
            overall_score=65.0,
            fit_summary="测试报告",
            confidence="medium",
        )
        session.add(obj)
        session.commit()
        session.refresh(obj)
        _test_report_ids.append((obj.id, jp.id, cp.id))
        return obj.id


def _delete_test_reports():
    """Helper: 清理测试数据（先删子表，再删父表）"""
    from models.database import SessionLocal
    from models.profile import FitAnalysisReport, JobProfile, CandidateProfile
    with SessionLocal() as session:
        for rid, jid, cid in _test_report_ids:
            # 删所有关联到该 job_profile / candidate_profile 的 report（含 rerun 创建的）
            session.query(FitAnalysisReport).filter(FitAnalysisReport.job_profile_id == jid).delete(synchronize_session=False)
            session.query(FitAnalysisReport).filter(FitAnalysisReport.candidate_profile_id == cid).delete(synchronize_session=False)
            session.query(JobProfile).filter(JobProfile.id == jid).delete()
            session.query(CandidateProfile).filter(CandidateProfile.id == cid).delete()
        session.commit()
    _test_report_ids.clear()


def test_list_reports():
    """GET /fit_analysis_reports 能按 user_id 返回列表"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    rid = _create_test_report()
    try:
        uid = _ensure_test_user()
        r = c.get(f'/fit_analysis_reports?user_id={uid}')
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 1
        assert any(i["id"] == rid for i in items)
    finally:
        _delete_test_reports()


def test_list_reports_job_filter():
    """GET /fit_analysis_reports 支持 job_name 过滤"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    _create_test_report()
    try:
        uid = _ensure_test_user()
        r = c.get(f'/fit_analysis_reports?user_id={uid}&job_name=不存在的岗位')
        assert r.status_code == 200
        assert r.json()["total"] == 0
    finally:
        _delete_test_reports()


def test_delete_report():
    """DELETE /fit_analysis_reports/{id} 成功删除"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    rid = _create_test_report()
    try:
        r = c.delete(f'/fit_analysis_reports/{rid}')
        assert r.status_code == 200
        assert r.json()["code"] == 200
        # 确认已删除（内部 code=404）
        r2 = c.get(f'/fit_analysis_reports/{rid}')
        assert r2.json()["code"] == 404
    finally:
        _delete_test_reports()


def test_delete_nonexistent():
    """DELETE 不存在 id 返回 404"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    r = c.delete('/fit_analysis_reports/999999')
    assert r.status_code == 404


def test_delete_other_user_report():
    """DELETE 带 user_id 时不能删除别人的报告"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    rid = _create_test_report()
    try:
        r = c.delete(f'/fit_analysis_reports/{rid}?user_id=12345')  # 不是测试用户
        assert r.status_code == 404
        # 报告仍在
        r2 = c.get(f'/fit_analysis_reports/{rid}')
        assert r2.status_code == 200
    finally:
        _delete_test_reports()


def test_rerun_report():
    """POST /fit_analysis_reports/{id}/rerun 会创建新报告"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    rid = _create_test_report()
    try:
        uid = _ensure_test_user()
        r = c.post(f'/fit_analysis_reports/{rid}/rerun', json={"user_id": uid})
        assert r.status_code == 200
        assert r.json()["code"] == 200
        assert r.json()["new_report_id"] != rid  # 新报告，不覆盖旧报告
    finally:
        _delete_test_reports()


def test_rerun_nonexistent():
    """rerun 不存在 id 返回 404"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    uid = _ensure_test_user()
    r = c.post('/fit_analysis_reports/999999/rerun', json={"user_id": uid})
    assert r.status_code == 404


def test_get_report_not_broken():
    """旧 GET /fit_analysis_reports/{id} 接口不被破坏"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    rid = _create_test_report()
    try:
        r = c.get(f'/fit_analysis_reports/{rid}')
        assert r.json()["code"] == 200
        report = r.json()["report"]
        assert report["overall_fit_level"] == "moderate"
        assert report["overall_score"] == 65.0
    finally:
        _delete_test_reports()


def test_fit_logic_unchanged():
    """FitAnalysis 评分逻辑不变"""
    from services.fit_analysis_service import analyze_fit
    from services.profile_schemas import JobProfileResult, CandidateProfileResult
    job = JobProfileResult(job_name="Python后端", must_have_capabilities=["Python", "FastAPI"])
    cand = CandidateProfileResult(skill_stack=[{"skill": "Python"}, {"skill": "FastAPI"}])
    result = analyze_fit(job, cand)
    assert result.overall_score > 0
    assert result.overall_fit_level in ("strong", "moderate", "weak")


def test_golden_eval_not_degraded():
    """Golden Set 不退化"""
    from eval.run_golden_eval import run_golden_eval
    report = run_golden_eval(limit=5)
    assert report["summary"]["pass_rate"] >= 80
    assert report["summary"]["avg_score"] >= 70
