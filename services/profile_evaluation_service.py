"""Profile evaluation service — v0.13 人工评估集 + 质量反馈闭环"""
from __future__ import annotations
from datetime import datetime
from core.logger import get_logger

logger = get_logger(__name__)

VALID_TARGET_TYPES = {"job_profile", "candidate_profile", "fit_analysis_report"}
VALID_ERROR_TYPES = {"", "missing_info", "wrong_info", "hallucination", "weak_evidence", "bad_suggestion", "unfair_judgment", "other"}


def create_evaluation(
    user_id: int,
    target_type: str,
    target_id: int,
    rating: int = 0,
    is_correct: bool = True,
    error_type: str = "",
    field_name: str = "",
    comment: str = "",
    useful_for_training: bool = False,
) -> int:
    """保存人工评估，返回 ID"""
    if target_type not in VALID_TARGET_TYPES:
        raise ValueError(f"无效 target_type: {target_type}")
    if rating and not (1 <= rating <= 5):
        raise ValueError(f"rating 必须 1-5，当前: {rating}")
    if error_type and error_type not in VALID_ERROR_TYPES:
        raise ValueError(f"无效 error_type: {error_type}")

    from models.database import SessionLocal
    from models.profile import ProfileEvaluation
    with SessionLocal() as session:
        obj = ProfileEvaluation(
            user_id=user_id,
            target_type=target_type,
            target_id=target_id,
            rating=rating,
            is_correct=is_correct,
            error_type=error_type,
            field_name=field_name,
            comment=comment,
            useful_for_training=useful_for_training,
        )
        session.add(obj)
        session.commit()
        session.refresh(obj)
        logger.info(f"评估已保存: {target_type}#{target_id} rating={rating}")
        return obj.id


def list_evaluations(
    target_type: str = "",
    target_id: int = 0,
    user_id: int = 0,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """查询评估列表"""
    from models.database import SessionLocal
    from models.profile import ProfileEvaluation
    with SessionLocal() as session:
        q = session.query(ProfileEvaluation)
        if target_type:
            q = q.filter(ProfileEvaluation.target_type == target_type)
        if target_id:
            q = q.filter(ProfileEvaluation.target_id == target_id)
        if user_id:
            q = q.filter(ProfileEvaluation.user_id == user_id)
        rows = q.order_by(ProfileEvaluation.created_at.desc()).offset(offset).limit(limit).all()
        return [{
            "id": r.id,
            "user_id": r.user_id,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "rating": r.rating,
            "is_correct": r.is_correct,
            "error_type": r.error_type,
            "field_name": r.field_name,
            "comment": r.comment,
            "useful_for_training": r.useful_for_training,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        } for r in rows]


def summarize_evaluations(
    target_type: str = "",
    user_id: int = 0,
    limit: int = 100,
) -> dict:
    """汇总评估统计"""
    from models.database import SessionLocal
    from models.profile import ProfileEvaluation
    from sqlalchemy import func as sqlfunc

    with SessionLocal() as session:
        q = session.query(ProfileEvaluation)
        if target_type:
            q = q.filter(ProfileEvaluation.target_type == target_type)
        if user_id:
            q = q.filter(ProfileEvaluation.user_id == user_id)

        total = q.count()
        if total == 0:
            return {
                "total_count": 0,
                "average_rating": 0,
                "correct_rate": 0,
                "error_type_counts": {},
                "recent_items": [],
            }

        avg_rating = q.filter(ProfileEvaluation.rating > 0).with_entities(
            sqlfunc.avg(ProfileEvaluation.rating)
        ).scalar() or 0

        correct_count = q.filter(ProfileEvaluation.is_correct == True).count()
        correct_rate = round(correct_count / total, 3) if total else 0

        error_rows = q.filter(ProfileEvaluation.error_type != "").with_entities(
            ProfileEvaluation.error_type,
            sqlfunc.count(),
        ).group_by(ProfileEvaluation.error_type).all()
        error_type_counts = {r[0]: r[1] for r in error_rows}

        recent = q.order_by(ProfileEvaluation.created_at.desc()).limit(min(limit, 10)).all()
        recent_items = [{
            "id": r.id,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "rating": r.rating,
            "is_correct": r.is_correct,
            "error_type": r.error_type,
            "comment": r.comment[:80] if r.comment else "",
        } for r in recent]

    return {
        "total_count": total,
        "average_rating": round(float(avg_rating), 2),
        "correct_rate": correct_rate,
        "error_type_counts": error_type_counts,
        "recent_items": recent_items,
    }
