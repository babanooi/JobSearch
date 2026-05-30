"""JD 知识库存储 —— 切分 → embedding → MySQL + ChromaDB 双写"""
import hashlib
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter
from models.database import SessionLocal
from models.document import JdDocument, JdChunk
from core.logger import get_logger

logger = get_logger(__name__)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_company(title: str) -> str:
    """从搜索标题中提取公司名，如 'Java后端 - XX科技有限公司'"""
    if not title:
        return ""
    for sep in (" - ", "｜", " | ", "·"):
        parts = title.rsplit(sep, maxsplit=1)
        if len(parts) == 2 and len(parts[1]) <= 30:
            return parts[1].strip()
    return ""


class JDStore:
    def __init__(self, embeddings, db_session_factory, chroma_client):
        self.embeddings = embeddings
        self.db_factory = db_session_factory
        self.chroma = chroma_client
        self.collection = chroma_client.get_or_create_collection(
            name="jd_chunks",
            metadata={"hnsw:space": "cosine"},
        )
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", "。", ".", "；", ";", "，", ",", " ", ""],
        )

    def store_jd(self, job_name: str, jd_items: list[dict]) -> int:
        """存一批 JD，去重后返回实际新增的 chunk 数"""
        new_chunk_records = []  # [{"chunk_text": str, "chunk_id": int, "doc": {...}}, ...]

        with self.db_factory() as session:
            for item in jd_items:
                raw_text = (item.get("content") or "").strip()
                if not raw_text:
                    continue

                h = _text_hash(raw_text)
                existing = session.query(JdDocument).filter(
                    JdDocument.text_hash == h
                ).first()
                if existing:
                    logger.debug(f"JD 去重跳过: {item.get('title', '')[:40]}")
                    continue

                doc = JdDocument(
                    job_name=job_name,
                    source_url=item.get("url", ""),
                    title=item.get("title", ""),
                    company=_parse_company(item.get("title", "")),
                    raw_text=raw_text,
                    text_hash=h,
                )
                session.add(doc)
                session.flush()

                chunks = self.splitter.split_text(raw_text)
                for idx, chunk_text in enumerate(chunks):
                    ch = JdChunk(
                        document_id=doc.id,
                        chunk_index=idx,
                        chunk_text=chunk_text,
                        chunk_hash=_text_hash(chunk_text),
                        token_count=len(chunk_text),
                    )
                    session.add(ch)
                    session.flush()
                    # 在 session 关闭前提取所有需要的数据
                    new_chunk_records.append({
                        "chunk_id": ch.id,
                        "chunk_text": chunk_text,
                        "chunk_index": idx,
                        "document_id": doc.id,
                        "job_name": doc.job_name,
                        "company": doc.company or "",
                        "source_url": doc.source_url or "",
                        "fetched_at": doc.fetched_at.isoformat() if doc.fetched_at else "",
                    })

            session.commit()

        if not new_chunk_records:
            return 0

        # 批量 embedding
        texts = [r["chunk_text"] for r in new_chunk_records]
        try:
            vectors = self.embeddings.embed_documents(texts)
        except Exception as e:
            logger.warning(f"Embedding 失败（ChromaDB 未写入）: {e}")
            return len(new_chunk_records)

        # ChromaDB 写入
        try:
            self.collection.add(
                ids=[f"chunk_{r['chunk_id']}" for r in new_chunk_records],
                embeddings=vectors,
                metadatas=[{
                    "document_id": r["document_id"],
                    "job_name": r["job_name"],
                    "company": r["company"],
                    "chunk_index": r["chunk_index"],
                    "source_url": r["source_url"],
                    "fetched_at": r["fetched_at"],
                } for r in new_chunk_records],
                documents=texts,
            )
        except Exception as e:
            logger.warning(f"ChromaDB 写入失败: {e}")
            return len(new_chunk_records)

        # 回填 chroma_id
        with self.db_factory() as session:
            for r in new_chunk_records:
                session.query(JdChunk).filter(
                    JdChunk.id == r["chunk_id"]
                ).update({"chroma_id": f"chunk_{r['chunk_id']}"})
            session.commit()

        return len(new_chunk_records)
