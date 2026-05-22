import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.sql import func
from models.database import Base


class JdDocument(Base):
    __tablename__ = "jd_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_name: Mapped[str] = mapped_column(String(255), index=True, comment="关联岗位名")
    source_url: Mapped[str] = mapped_column(String(500), nullable=True, comment="招聘页面 URL")
    title: Mapped[str] = mapped_column(String(255), nullable=True, comment="JD 标题")
    company: Mapped[str] = mapped_column(String(255), nullable=True, comment="公司名")
    raw_text: Mapped[str] = mapped_column(Text, comment="JD 完整原文")
    text_hash: Mapped[str] = mapped_column(String(64), index=True, unique=True, comment="SHA256 去重指纹")
    search_query: Mapped[str] = mapped_column(String(500), nullable=True, comment="搜索关键词")
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="抓取时间"
    )


class JdChunk(Base):
    __tablename__ = "jd_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jd_documents.id"), index=True, comment="关联文档 ID"
    )
    chunk_index: Mapped[int] = mapped_column(Integer, comment="块序号（从 0 开始）")
    chunk_text: Mapped[str] = mapped_column(Text, comment="文本块内容")
    chunk_hash: Mapped[str] = mapped_column(String(64), index=True, unique=True, comment="SHA256 去重指纹")
    token_count: Mapped[int] = mapped_column(Integer, default=0, comment="估算 token 数")
    chroma_id: Mapped[str] = mapped_column(String(255), nullable=True, comment="ChromaDB 中对应的 embedding ID")
