"""② 短期对话记忆 —— SqliteSaver 持久化对话上下文 + LLM 摘要压缩"""
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.prompts import PromptTemplate

from agents.base import get_heavy_llm
from core.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "checkpoints.db"
MAX_MESSAGE_ROUNDS = 10

SUMMARIZE_PROMPT = PromptTemplate.from_template("""
你是对话摘要专家。将以下求职助手与用户的对话压缩为结构化摘要。

规则：
1. **先过滤**：忽略与求职/岗位/技能/技术无关的闲聊（如天气、娱乐）
2. **再压缩**：对剩余相关消息进行摘要
3. 如有历史摘要，请与新旧消息合并，形成一份完整摘要，总字数 ≤ 300 字
4. 输出格式如下（缺的信息填"未知"）：
   - 岗位方向：[...]
   - 已分析岗位：[...]
   - 技能提及：[...]
   - 偏好（薪资/城市/行业）：[...]
   - 待办：[...]

{previous_summary}
对话记录：
{messages}
""")

PREVIOUS_SUMMARY_PREFIX = "历史摘要（请与新对话合并）：\n"


def create_checkpointer() -> SqliteSaver:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    return SqliteSaver(conn)


def list_checkpoint_threads(limit: int = 100) -> list[dict]:
    """从 LangGraph checkpoint 库列出可恢复的非 research 会话 thread。"""
    if not DB_PATH.exists():
        return []
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            rows = conn.execute(
                """
                SELECT thread_id, COUNT(*) AS checkpoint_count, MAX(checkpoint_id) AS latest_checkpoint
                FROM checkpoints
                WHERE thread_id NOT LIKE 'research_%'
                GROUP BY thread_id
                ORDER BY latest_checkpoint DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except Exception as e:
        logger.warning(f"列出 checkpoint 会话失败: {e}")
        return []

    return [
        {
            "thread_id": r[0],
            "checkpoint_count": r[1],
            "latest_checkpoint": r[2],
        }
        for r in rows
    ]


def load_messages_from_writes(thread_id: str) -> list[dict]:
    """Fallback reader for older LangGraph checkpoints.

    Some saved conversations have `messages` in the `writes` table, while
    `graph.get_state()` may return an empty state after graph/schema changes.
    This reads the latest serialized messages write directly.
    """
    if not thread_id or not DB_PATH.exists():
        return []
    try:
        import ormsgpack
    except Exception as e:
        logger.warning(f"ormsgpack 不可用，无法从 writes 恢复消息: {e}")
        return []

    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                """
                SELECT value
                FROM writes
                WHERE thread_id = ? AND channel = 'messages' AND type = 'msgpack'
                ORDER BY checkpoint_id DESC, idx DESC
                LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
    except Exception as e:
        logger.warning(f"从 writes 查询消息失败: {e}")
        return []

    if not row or not row[0]:
        return []

    try:
        raw_messages = ormsgpack.unpackb(row[0])
    except Exception as e:
        logger.warning(f"从 writes 反序列化消息失败: {e}")
        return []

    messages = []
    for msg in raw_messages or []:
        if isinstance(msg, dict):
            role = msg.get("role") or msg.get("type") or ""
            content = msg.get("content") or ""
        else:
            role = getattr(msg, "role", "") or getattr(msg, "type", "")
            content = getattr(msg, "content", "")
        if role and content:
            messages.append({"role": str(role), "content": str(content)})
    return messages


def prune_old_checkpoints(thread_id: str):
    """压缩后清理旧快照，只保留当前状态"""
    checkpointer = create_checkpointer()
    try:
        checkpointer.prune([thread_id], strategy="keep_latest")
        logger.debug(f"checkpoint 清理: thread={thread_id[:8]}...")
    except Exception as e:
        logger.warning(f"checkpoint 清理失败: {e}")


def delete_checkpoint_thread(thread_id: str):
    """删除指定 thread_id 的所有 checkpoint 数据（会话彻底删除时调用）"""
    if not DB_PATH.exists():
        return
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            conn.commit()
            logger.info(f"checkpoint 删除: thread={thread_id[:8]}...")
    except Exception as e:
        logger.warning(f"checkpoint 删除失败: {e}")


def compress_history(messages: list[dict], max_rounds: int = MAX_MESSAGE_ROUNDS,
                     previous_summary: str = "") -> dict:
    """
   摘要压缩 滑动窗口 + （一次 LLM 调用完成过滤+压缩）
    Prompt 中要求 LLM 先忽略无关闲聊，再对求职相关内容进行摘要
    """
    if len(messages) <= max_rounds * 2:
        return {"summary": previous_summary or "", "recent": messages}

    old = messages[:-(max_rounds * 2)]
    recent = messages[-(max_rounds * 2):]

    flat = "\n".join(
        f"{'用户' if m['role'] == 'user' else '助手'}: {m['content']}"
        for m in old
    )
    prev_block = f"{PREVIOUS_SUMMARY_PREFIX}{previous_summary}\n\n" if previous_summary else ""
    chain = SUMMARIZE_PROMPT | get_heavy_llm()
    try:
        summary = chain.invoke({
            "messages": flat,
            "previous_summary": prev_block,
        }).content.strip()
        logger.info(f"短期记忆压缩: {len(old)} 条 → {len(summary)} 字摘要（含历史合并）")
    except Exception as e:
        logger.warning(f"摘要压缩失败: {e}")
        summary = previous_summary

    return {"summary": summary, "recent": recent}


def merge_context(summary: str, recent: list[dict], knowledge: list[str]) -> str:
    """合并摘要 + 最近对话 + 知识库检索结果，生成 LLM 上下文"""
    parts = []
    if summary:
        parts.append(f"## 历史对话摘要\n{summary}")
    if knowledge:
        parts.append("## 相关知识库\n" + "\n---\n".join(knowledge))
    if recent:
        parts.append("## 最近对话\n" + "\n".join(
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content']}"
            for m in recent
        ))
    return "\n\n".join(parts)
