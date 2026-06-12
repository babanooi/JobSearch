"""v0.23 Fit report detail + pagination tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_USER_ID = 0
_test_records = []  # (report_id, jp_id, cp_id)


def _ensure_test_user():
    global TEST_USER_ID
    if TEST_USER_ID:
        return TEST_USER_ID
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    r = c.get("/user?username=test_detail_user")
    TEST_USER_ID = r.json().get("user_id", 1)
    return TEST_USER_ID


def _create_report():
    uid = _ensure_test_user()
    from models.database import SessionLocal
    from models.profile import FitAnalysisReport, JobProfile, CandidateProfile
    import json
    with SessionLocal() as s:
        jp = JobProfile(job_name="测试岗位v23", confidence="medium", must_have_capabilities='["Python","SQL"]')
        s.add(jp); s.flush()
        cp = CandidateProfile(user_id=uid, confidence="medium", skill_stack='[{"skill":"Python"}]')
        s.add(cp); s.flush()
        rp = FitAnalysisReport(
            user_id=uid, job_profile_id=jp.id, candidate_profile_id=cp.id,
            overall_fit_level="moderate", overall_score=72.0, fit_summary="v23测试",
            confidence="medium", strengths='["Python匹配"]', gaps='["SQL缺失"]',
        )
        s.add(rp); s.commit(); s.refresh(rp)
        _test_records.append((rp.id, jp.id, cp.id))
        return rp.id, jp.id, cp.id


def _cleanup():
    from models.database import SessionLocal
    from models.profile import FitAnalysisReport, JobProfile, CandidateProfile
    with SessionLocal() as s:
        for rid, jid, cid in _test_records:
            s.query(FitAnalysisReport).filter(FitAnalysisReport.job_profile_id == jid).delete(synchronize_session=False)
            s.query(JobProfile).filter(JobProfile.id == jid).delete()
            s.query(CandidateProfile).filter(CandidateProfile.id == cid).delete()
        s.commit()
    _test_records.clear()


def test_detail_returns_profiles():
    """GET /fit_analysis_reports/{id} 返回 report + job_profile + candidate_profile"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    rid, jid, cid = _create_report()
    try:
        r = c.get(f'/fit_analysis_reports/{rid}')
        d = r.json()
        assert d["code"] == 200
        assert d["report"]["overall_score"] == 72.0
        assert d["job_profile"] is not None
        assert d["job_profile"]["job_name"] == "测试岗位v23"
        assert d["candidate_profile"] is not None
        assert len(d["warnings"]) == 0
    finally:
        _cleanup()


def test_detail_json_fields_parsed():
    """JSON 字段被解析为 list/dict，不是字符串"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    rid, jid, cid = _create_report()
    try:
        r = c.get(f'/fit_analysis_reports/{rid}')
        d = r.json()
        assert isinstance(d["report"]["strengths"], list)
        assert isinstance(d["job_profile"]["must_have_capabilities"], list)
        assert isinstance(d["candidate_profile"]["skill_stack"], list)
    finally:
        _cleanup()


def test_detail_returns_profiles_and_warnings():
    """详情接口返回 report + job_profile + candidate_profile + warnings"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    uid = _ensure_test_user()
    from models.database import SessionLocal
    from models.profile import FitAnalysisReport, JobProfile, CandidateProfile
    with SessionLocal() as s:
        jp = JobProfile(job_name="详情测试岗位", confidence="medium"); s.add(jp); s.flush()
        cp = CandidateProfile(user_id=uid, confidence="medium"); s.add(cp); s.flush()
        rp = FitAnalysisReport(user_id=uid, job_profile_id=jp.id, candidate_profile_id=cp.id,
                               overall_fit_level="moderate", overall_score=50, fit_summary="详情测试", confidence="medium")
        s.add(rp); s.commit(); s.refresh(rp)
        rid, jid, cid = rp.id, jp.id, cp.id
    try:
        r = c.get(f'/fit_analysis_reports/{rid}')
        d = r.json()
        assert d["code"] == 200
        assert d["report"]["overall_score"] == 50
        assert d["job_profile"] is not None
        assert d["job_profile"]["job_name"] == "详情测试岗位"
        assert d["candidate_profile"] is not None
        assert len(d["warnings"]) == 0
    finally:
        with SessionLocal() as s:
            s.query(FitAnalysisReport).filter(FitAnalysisReport.id == rid).delete()
            s.query(JobProfile).filter(JobProfile.id == jid).delete()
            s.query(CandidateProfile).filter(CandidateProfile.id == cid).delete()
            s.commit()


def test_list_has_pagination():
    """GET /fit_analysis_reports 返回 has_more / next_offset"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    uid = _ensure_test_user()
    r = c.get(f'/fit_analysis_reports?user_id={uid}&limit=2')
    d = r.json()
    assert d["code"] == 200
    assert "has_more" in d
    assert "next_offset" in d
    assert d["limit"] == 2


def test_list_limit_max_50():
    """limit>50 被 FastAPI 参数校验拒绝"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    uid = _ensure_test_user()
    r = c.get(f'/fit_analysis_reports?user_id={uid}&limit=100')
    assert r.status_code == 422


def test_list_job_filter():
    """job_name 筛选仍可用"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    uid = _ensure_test_user()
    r = c.get(f'/fit_analysis_reports?user_id={uid}&job_name=不存在的岗位')
    d = r.json()
    assert d["total"] == 0


def test_detail_old_endpoint_not_broken():
    """旧 GET /fit_analysis_reports/{id} 接口兼容"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    rid, jid, cid = _create_report()
    try:
        r = c.get(f'/fit_analysis_reports/{rid}')
        d = r.json()
        assert d["code"] == 200
        assert "report" in d
        assert d["report"]["overall_fit_level"] == "moderate"
    finally:
        _cleanup()


def test_delete_and_rerun_still_work():
    """DELETE / rerun 旧接口不被破坏"""
    from api.fastapi_app import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    rid, jid, cid = _create_report()
    uid = _ensure_test_user()
    try:
        # DELETE
        r1 = c.delete(f'/fit_analysis_reports/{rid}')
        assert r1.status_code == 200
        # rerun（旧报告已删，rerun 应返回 404）
        r2 = c.post(f'/fit_analysis_reports/{rid}/rerun', json={"user_id": uid})
        assert r2.status_code == 404
    finally:
        _cleanup()
