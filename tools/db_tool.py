from setting import settings
import datetime
from sqlalchemy import select
from sqlalchemy.sql import func
from database.db import SessionLocal, JobSkills
from collections import Counter
from utils.logger import get_logger

logger = get_logger(__name__)


class DBTool:
    @staticmethod
    def save_skill_list(job_name: str, skill_list: list[str]):
        """批量保存岗位技能"""
        with SessionLocal() as db_session:
            try:
                db_session.query(JobSkills).filter(JobSkills.job_name == job_name).delete()
                skill_count = Counter(skill_list)

                for skill_name, count in skill_count.items():
                    cleaned_skill = skill_name.strip()
                    if cleaned_skill:
                        skill_object = JobSkills(
                            job_name=job_name,
                            skill_name=cleaned_skill,
                            count=count
                        )
                        db_session.add(skill_object)
                db_session.commit()
                logger.info(f"DBTool 入库: {job_name} → {len(skill_count)} 个技能")
            except Exception as e:
                db_session.rollback()
                logger.error(f"DBTool 入库失败: {job_name} | {e}", exc_info=True)
                raise e

    @staticmethod
    def get_skill_rank(job_name: str, top_n: int = 10) -> list[str]:
        """查询岗位技能热度"""
        with SessionLocal() as db_session:
            try:
                skill_count = (
                    db_session.query(JobSkills)
                    .filter(JobSkills.job_name == job_name)
                    .order_by(JobSkills.count.desc())
                    .limit(top_n)
                    .all()
                )
                logger.debug(f"DBTool 查询: {job_name} top{top_n}")
                return [{"skill": raw.skill_name, "count": raw.count} for raw in skill_count]
            except Exception as e:
                db_session.rollback()
                logger.error(f"DBTool 查询失败: {job_name} | {e}", exc_info=True)
                raise e
