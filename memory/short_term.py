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
3. 输出格式如下（缺的信息填"未知"）：
   - 岗位方向：[...]
   - 已分析岗位：[...]
   - 技能提及：[...]
   - 偏好（薪资/城市/行业）：[...]
   - 待办：[...]
4. 总字数 ≤ 200 字

对话记录：
{messages}
""")


def create_checkpointer() -> SqliteSaver:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    return SqliteSaver(conn)


def prune_old_checkpoints(thread_id: str):
    """压缩后清理旧快照，只保留当前状态"""
    checkpointer = create_checkpointer()
    try:
        checkpointer.prune([thread_id], strategy="keep_latest")
        logger.debug(f"checkpoint 清理: thread={thread_id[:8]}...")
    except Exception as e:
        logger.warning(f"checkpoint 清理失败: {e}")


def compress_history(messages: list[dict], max_rounds: int = MAX_MESSAGE_ROUNDS) -> dict:
    """
   摘要压缩 滑动窗口 + （一次 LLM 调用完成过滤+压缩）
    Prompt 中要求 LLM 先忽略无关闲聊，再对求职相关内容进行摘要
    """
    if len(messages) <= max_rounds * 2:
        return {"summary": "", "recent": messages}

    old = messages[:-(max_rounds * 2)]
    recent = messages[-(max_rounds * 2):]

    flat = "\n".join(
        f"{'用户' if m['role'] == 'user' else '助手'}: {m['content']}"
        for m in old
    )
    chain = SUMMARIZE_PROMPT | get_heavy_llm()
    try:
        summary = chain.invoke({"messages": flat}).content.strip()
        logger.info(f"短期记忆压缩: {len(old)} 条 → {len(summary)} 字摘要（含自动过滤）")
    except Exception as e:
        logger.warning(f"摘要压缩失败: {e}")
        summary = ""

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
