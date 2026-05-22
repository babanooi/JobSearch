"""① 工作记忆 —— AgentState 工厂，管理单次工作流内的节点间共享状态"""
from typing import TypedDict, List, Optional


class AgentState(TypedDict):
    job_name: str
    search_raw_items: Optional[List[dict]]
    skill_list: List[str]
    status: str
    search_round: int
    search_query: str
    next_node: Optional[str]


def init_state(job_name: str) -> AgentState:
    """创建初始工作记忆"""
    return {
        "job_name": job_name,
        "search_raw_items": None,
        "skill_list": [],
        "status": "开始执行",
        "search_round": 0,
        "search_query": "",
        "next_node": None,
    }
