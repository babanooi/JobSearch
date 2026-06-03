import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.sql import func
from models.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, comment="用户名")
    password_hash: Mapped[str] = mapped_column(String(255), comment="bcrypt 哈希")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True, comment="归属用户")
    thread_id: Mapped[str] = mapped_column(String(36), index=True, comment="LangGraph checkpoint 标识")
    title: Mapped[str] = mapped_column(String(100), default="", comment="对话标题")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="最后活跃时间"
    )


class Summary(Base):
    __tablename__ = "conversation_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    thread_id: Mapped[str] = mapped_column(String(36), index=True, comment="关联对话 thread_id")
    summary_text: Mapped[str] = mapped_column(Text, comment="LLM 生成的摘要")
    start_round: Mapped[int] = mapped_column(Integer, default=0, comment="摘要覆盖的起始轮次")
    end_round: Mapped[int] = mapped_column(Integer, default=0, comment="摘要覆盖的结束轮次")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="生成时间"
    )
