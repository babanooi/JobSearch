from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.sql import func
from setting import settings
import datetime

# --- 1. 异步引擎与会话工厂 ---
engine = create_engine(
    settings.DATABASE_URL,
    echo=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)

# --- 2. 基类（带创建时间）---
class Base(DeclarativeBase):
    create_time: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        comment="创建时间"
    )

# --- 3. 数据表模型 ---
class JobSkills(Base):
    __tablename__ = "job_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_name: Mapped[str] = mapped_column(String(255), index=True, comment="岗位名称")
    skill_name: Mapped[str] = mapped_column(String(255), index=True, comment="技能关键词")
    count: Mapped[int] = mapped_column(Integer, comment="技能热度")
# --- 4. 初始化建表函数 ---
def init_database():
    Base.metadata.create_all(bind=engine)
# --- 5. 获取数据库会话的依赖 ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
