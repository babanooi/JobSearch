"""全链路调用追踪 —— 记录每次 LLM 调用的节点、耗时、Token 消耗"""
import time
import json
from pathlib import Path
from contextlib import contextmanager
from core.logger import get_logger

logger = get_logger(__name__)

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "trace.jsonl"


@contextmanager
def trace(node: str, purpose: str, model: str = ""):
    """埋点上下文管理器"""
    t0 = time.time()
    record = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "node": node,
        "purpose": purpose,
        "model": model,
    }
    try:
        yield record
        record["status"] = "ok"
    except Exception as e:
        record["status"] = f"fail:{e}"
        raise
    finally:
        record["elapsed_ms"] = round((time.time() - t0) * 1000)
        _write(record)


def _write(record: dict):
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"trace 写入失败: {e}")


def read_traces(limit: int = 50) -> list[dict]:
    """读取最近 N 条追踪记录"""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    records = []
    for line in lines[-limit:]:
        try:
            records.append(json.loads(line))
        except Exception:
            pass
    return records


def trace_summary(thread_id: str = "") -> dict:
    """汇总统计：总耗时、总 Token、各节点耗时分布"""
    records = read_traces(500)
    if thread_id:
        records = [r for r in records if r.get("thread_id") == thread_id]
    if not records:
        return {"total_calls": 0}

    total_ms = sum(r.get("elapsed_ms", 0) for r in records)
    total_tokens = sum(
        (r.get("tokens_prompt", 0) + r.get("tokens_completion", 0))
        for r in records
    )
    by_node = {}
    for r in records:
        node = r.get("node", "?")
        if node not in by_node:
            by_node[node] = {"calls": 0, "total_ms": 0}
        by_node[node]["calls"] += 1
        by_node[node]["total_ms"] += r.get("elapsed_ms", 0)

    return {
        "total_calls": len(records),
        "total_ms": total_ms,
        "total_sec": round(total_ms / 1000, 1),
        "total_tokens": total_tokens,
        "by_node": by_node,
    }
