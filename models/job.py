import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, DateTime
from sqlalchemy.sql import func
from models.database import Base


class JobSkills(Base):
    __tablename__ = "job_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_name: Mapped[str] = mapped_column(String(255), index=True, comment="岗位名称")
    skill_name: Mapped[str] = mapped_column(String(255), index=True, comment="技能关键词")
    count: Mapped[int] = mapped_column(Integer, comment="技能热度（最近一次快照）")
    total_jds: Mapped[int] = mapped_column(Integer, default=0, comment="快照时的 JD 样本量")
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="最近一次分析中出现的时间"
    )
