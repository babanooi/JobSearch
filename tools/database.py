import datetime
from collections import Counter
from models.database import SessionLocal
from models.job import JobSkills
from tools.skill_guard import normalize_job_name
from core.logger import get_logger

logger = get_logger(__name__)


class DBTool:
    @staticmethod
    def save_skill_list(job_name: str, skill_list: list[str], total_jds: int = 0):
        """UPSERT 策略：新增技能 INSERT，已有技能 UPDATE 频次+时间戳+样本量，旧技能保留"""
        job_name = normalize_job_name(job_name)
        with SessionLocal() as db_session:
            try:
                skill_count = Counter(skill_list)
                now = datetime.datetime.now()
                updated = 0
                inserted = 0

                for skill_name, count in skill_count.items():
                    cleaned = skill_name.strip()
                    if not cleaned:
                        continue
                    existing = (
                        db_session.query(JobSkills)
                        .filter(JobSkills.job_name == job_name)
                        .filter(JobSkills.skill_name == cleaned)
                        .first()
                    )
                    if existing:
                        existing.count = count
                        existing.total_jds = total_jds
                        existing.last_seen_at = now
                        updated += 1
                    else:
                        db_session.add(JobSkills(
                            job_name=job_name, skill_name=cleaned,
                            count=count, total_jds=total_jds, last_seen_at=now,
                        ))
                        inserted += 1

                db_session.commit()
                logger.info(
                    f"DBTool 入库: {job_name} -> "
                    f"新增 {inserted} 更新 {updated}，共 {len(skill_count)} 个技能（样本 {total_jds} 条 JD）"
                )
            except Exception as e:
                db_session.rollback()
                logger.error(f"DBTool 入库失败: {job_name} | {e}", exc_info=True)
                raise

    @staticmethod
    def get_skill_rank(job_name: str, top_n: int = 10) -> list[dict]:
        job_name = normalize_job_name(job_name)
        with SessionLocal() as db_session:
            try:
                rows = (
                    db_session.query(JobSkills)
                    .filter(JobSkills.job_name == job_name)
                    .order_by(JobSkills.count.desc())
                    .limit(top_n)
                    .all()
                )
                return [
                    {
                        "skill": r.skill_name,
                        "count": r.count,
                        "total_jds": r.total_jds,
                        "last_seen_at": r.last_seen_at.strftime("%Y-%m-%d %H:%M") if r.last_seen_at else "",
                    }
                    for r in rows
                ]
            except Exception as e:
                db_session.rollback()
                logger.error(f"DBTool 查询失败: {job_name} | {e}", exc_info=True)
                raise
