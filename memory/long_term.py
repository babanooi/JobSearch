"""③ 长期记忆 —— 用户体系 + ChromaDB 检索 + MySQL 结构化查询"""
import re
import math
import chromadb
from pathlib import Path
from functools import lru_cache
from collections import defaultdict
from sqlalchemy import text
from models.database import SessionLocal
from models.document import JdChunk
from models.user import Summary, User, Conversation
from agents.base import get_utility_llm
from tools.skill_guard import normalize_job_name
from core.logger import get_logger

logger = get_logger(__name__)

CHROMA_PATH = Path(__file__).resolve().parent.parent / "data" / "chroma_db"

QUERY_SIMILARITY_THRESHOLD = 0.6
RRF_K = 60  # RRF 重排常数


def get_chroma_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


def search_jd_semantic(query: str, embeddings, top_k: int = 5) -> list[dict]:
    """ChromaDB 语义检索 JD 文本块"""
    client = get_chroma_client()
    try:
        col = client.get_collection("jd_chunks")
    except Exception:
        return []

    vec = embeddings.embed_query(query)
    results = col.query(query_embeddings=[vec], n_results=top_k)
    if not results.get("ids") or not results["ids"][0]:
        return []

    items = []
    for i, cid in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][i] if results.get("metadatas") else {}
        doc = results["documents"][0][i] if results.get("documents") else ""
        items.append({
            "chunk_id": cid,
            "text": doc,
            "job_name": meta.get("job_name", ""),
            "company": meta.get("company", ""),
            "source_url": meta.get("source_url", ""),
            "score": results["distances"][0][i] if results.get("distances") else 0,
        })
    return items


def query_skill_rank(job_name: str, top_n: int = 10) -> list[dict]:
    """MySQL 精确查询技能排名"""
    job_name = normalize_job_name(job_name)
    with SessionLocal() as session:
        rows = session.execute(
            text(
                "SELECT skill_name, count, total_jds FROM job_skills "
                "WHERE job_name = :job ORDER BY count DESC LIMIT :n"
            ),
            {"job": job_name, "n": top_n},
        ).fetchall()
        return [{"skill": r[0], "count": r[1], "total_jds": r[2]} for r in rows]


def list_analyzed_jobs() -> list[str]:
    """返回所有分析过的岗位名（去重）"""
    with SessionLocal() as session:
        rows = session.execute(
            text("SELECT DISTINCT job_name FROM job_skills ORDER BY job_name")
        ).fetchall()
    return [r[0] for r in rows]


def classify_rag_query(query: str) -> str:
    """一次轻量 LLM 调用，判断检索策略"""
    prompt = (
        "用户问: \"" + query[:200] + "\"\n"
        "分类为以下之一:\n"
        "structured - 问技能排名/出现次数/排行/哪些技能\n"
        "semantic   - 问具体技术怎么用/框架关系/做法/场景\n"
        "hybrid     - 既要排名概览又要具体JD来源\n"
        "meta       - 问有哪些岗位/有哪些公司/元数据\n"
        "只输出一个单词。"
    )
    try:
        result = get_utility_llm().invoke(prompt).content.strip().lower()
    except Exception:
        return "hybrid"
    if "structured" in result:
        return "structured"
    if "semantic" in result:
        return "semantic"
    if "meta" in result:
        return "meta"
    return "hybrid"


def match_job_names(query: str, embeddings, threshold: float = None) -> list[str]:
    """语义匹配已分析的岗位名（替代子串包含）"""
    if threshold is None:
        threshold = QUERY_SIMILARITY_THRESHOLD
    stored = list_analyzed_jobs()
    if not stored:
        return []
    try:
        query_vec = embeddings.embed_query(query)
        stored_vecs = embeddings.embed_documents(stored)
    except Exception:
        # embedding 失败时退化为子串匹配
        return [j for j in stored if any(w in query.lower() for w in j.lower().split())]

    from numpy import dot
    from numpy.linalg import norm

    matched = []
    for i, sv in enumerate(stored_vecs):
        sim = dot(query_vec, sv) / (norm(query_vec) * norm(sv))
        if sim >= threshold:
            matched.append((sim, stored[i]))
    matched.sort(key=lambda x: x[0], reverse=True)
    logger.debug(f"match_job_names: {len(matched)} 命中 (threshold={threshold})")
    return [m[1] for m in matched]


def list_jd_companies(job_name: str) -> list[str]:
    """返回某岗位相关的公司名（去重）"""
    with SessionLocal() as session:
        rows = session.execute(
            text(
                "SELECT DISTINCT company FROM jd_documents "
                "WHERE job_name = :job AND company != '' ORDER BY company"
            ),
            {"job": job_name},
        ).fetchall()
    return [r[0] for r in rows]


# ═══════════════════════════════════════════════════════════════
# BM25 关键词检索 + 向量检索 + RRF 重排（双路召回）
# ═══════════════════════════════════════════════════════════════

def _tokenize(text: str) -> list[str]:
    """中英文混合分词：中文 2-gram + 英文单词"""
    tokens = []
    # 英文单词
    tokens.extend(re.findall(r"[a-zA-Z+#.0-9]{2,}", text.lower()))
    # 中文 2-gram
    chinese = re.findall(r"[一-鿿]+", text)
    for seg in chinese:
        tokens.extend(seg[i:i+2] for i in range(len(seg) - 1))
    return tokens


class SimpleBM25:
    """轻量 BM25 关键词检索，无外部依赖"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs: list[str] = []
        self.doc_len: list[int] = []
        self.avgdl: float = 0
        self.idf: dict[str, float] = {}
        self.inverted: dict[str, list[tuple[int, int]]] = defaultdict(list)

    def fit(self, documents: list[str]):
        self.docs = documents
        N = len(documents)
        if N == 0:
            return
        for idx, doc in enumerate(documents):
            tokens = _tokenize(doc)
            self.doc_len.append(len(tokens))
            term_freq = defaultdict(int)
            for t in tokens:
                term_freq[t] += 1
            for term, freq in term_freq.items():
                self.inverted[term].append((idx, freq))
        self.avgdl = sum(self.doc_len) / N
        for term, postings in self.inverted.items():
            df = len(postings)
            self.idf[term] = math.log(1 + (N - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """返回 [(文档索引, BM25 分数), ...]"""
        if not self.docs:
            return []
        qtokens = _tokenize(query)
        scores = defaultdict(float)
        for term in set(qtokens):
            if term not in self.inverted:
                continue
            idf = self.idf[term]
            for doc_idx, freq in self.inverted[term]:
                dl = self.doc_len[doc_idx]
                tf = freq * (self.k1 + 1) / (freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
                scores[doc_idx] += idf * tf
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]


@lru_cache(maxsize=1)
def _load_bm25_index() -> SimpleBM25:
    """从 MySQL jd_chunks 加载所有文本，构建 BM25 索引（缓存）"""
    with SessionLocal() as session:
        rows = session.query(JdChunk.chunk_text).all()
    docs = [r[0] for r in rows]
    bm25 = SimpleBM25()
    bm25.fit(docs)
    logger.info(f"BM25 索引构建完成: {len(docs)} 个文档")
    return bm25


def _rrf_merge(
    bm25_ranked: list[tuple[int, float]],
    vector_items: list[dict],
    k: int = RRF_K,
) -> list[dict]:
    """RRF 重排：融合 BM25 和向量结果"""
    rrf_scores: dict[int, float] = {}
    chunk_id_to_item: dict[int, dict] = {}

    # BM25 贡献
    for rank, (doc_idx, _) in enumerate(bm25_ranked):
        rrf_scores[doc_idx] = rrf_scores.get(doc_idx, 0) + 1.0 / (k + rank + 1)

    # 向量贡献（按 chunk_id 关联到文档索引）
    for rank, item in enumerate(vector_items):
        cid = item.get("chunk_id", "")
        try:
            doc_idx = int(cid.replace("chunk_", ""))
        except ValueError:
            continue
        chunk_id_to_item[doc_idx] = item
        rrf_scores[doc_idx] = rrf_scores.get(doc_idx, 0) + 1.0 / (k + rank + 1)

    merged = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for doc_idx, score in merged:
        if doc_idx in chunk_id_to_item:
            item = chunk_id_to_item[doc_idx]
            # 余弦距离越小越相似，转为相似度分数便于展示
            cos_dist = item.get("score", 1.0)
            item["rrf_score"] = round(score, 4)
            item["cos_sim"] = round(1.0 - cos_dist, 4) if cos_dist <= 1.0 else 0
            results.append(item)

    return results


def hybrid_search_with_rerank(
    query: str,
    embeddings,
    top_k: int = 5,
) -> list[dict]:
    """BM25 + 向量双路召回 + RRF 重排，返回 Top-K 个 JD 文本块"""
    # 1. BM25 关键词检索
    bm25 = _load_bm25_index()
    bm25_ranked = bm25.search(query, top_k=top_k * 2)

    # 2. ChromaDB 向量检索
    vector_items = search_jd_semantic(query, embeddings, top_k=top_k * 2)

    # 3. RRF 重排
    merged = _rrf_merge(bm25_ranked, vector_items)
    logger.debug(
        f"hybrid_search: BM25={len(bm25_ranked)} + Vector={len(vector_items)}"
        f" -> RRF={len(merged)}"
    )
    return merged[:top_k]


def save_summary(thread_id: str, text: str):
    """压缩摘要写入 MySQL，跨会话持久化"""
    if not text or not thread_id:
        return
    with SessionLocal() as session:
        session.add(Summary(thread_id=thread_id, summary_text=text))
        session.commit()
    logger.info(f"摘要入库: thread={thread_id[:8]}... {len(text)} 字")


def load_latest_summary(thread_id: str) -> str:
    """从 MySQL 加载该 thread_id 的最新摘要"""
    with SessionLocal() as session:
        row = session.query(Summary).filter(
            Summary.thread_id == thread_id
        ).order_by(Summary.id.desc()).first()
    return row.summary_text if row else ""


# ═══════════════════════════════════════════════════════════════
# 用户体系：多用户对话隔离
# ═══════════════════════════════════════════════════════════════

def get_or_create_user(username: str) -> int:
    """获取或创建用户，返回 user_id"""
    with SessionLocal() as session:
        u = session.query(User).filter(User.username == username).first()
        if u:
            return u.id
        u = User(username=username, password_hash="")
        session.add(u)
        session.commit()
        session.refresh(u)
        return u.id


def list_user_conversations(user_id: int) -> list[dict]:
    """列出用户的所有对话（按活跃时间倒序）"""
    with SessionLocal() as session:
        rows = (
            session.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .all()
        )
    return [{
        "thread_id": r.thread_id,
        "title": r.title or "未命名对话",
        "created_at": r.created_at.strftime("%m-%d %H:%M") if r.created_at else "",
        "updated_at": r.updated_at.strftime("%m-%d %H:%M") if r.updated_at else "",
    } for r in rows]


def save_conversation(user_id: int, thread_id: str, title: str = ""):
    """新建或更新对话关联"""
    with SessionLocal() as session:
        conv = session.query(Conversation).filter(
            Conversation.thread_id == thread_id
        ).first()
        if conv:
            conv.title = title or conv.title
            from datetime import datetime
            conv.updated_at = datetime.now()
        else:
            session.add(Conversation(
                user_id=user_id, thread_id=thread_id, title=title
            ))
        session.commit()
