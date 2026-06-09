from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime
from sqlalchemy.sql import func
from core.config import settings
import datetime
import os

_engine = None
_session_factory = None


def get_engine():
    """懒加载 SQLAlchemy engine，首次调用时才创建"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.DATABASE_URL,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            pool_size=10,
            max_overflow=20,
            connect_args={"charset": "utf8mb4"},
        )
    return _engine


def get_session_factory():
    """懒加载 SessionLocal，首次调用时才创建"""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _session_factory


class _LazySessionLocal:
    """延迟代理：import 时不创建 engine，首次调用时才初始化"""
    def __call__(self):
        return get_session_factory()()
    def __getattr__(self, name):
        return getattr(get_session_factory(), name)


SessionLocal = _LazySessionLocal()


class Base(DeclarativeBase):
    create_time: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )


def init_database():
    """初始化数据库表结构"""
    # Ensure every ORM model is registered on Base.metadata before create_all().
    from models import document, job, profile, user  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def get_db():
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
