"""工作流状态定义"""
from typing import TypedDict, List, Optional


class AgentState(TypedDict):
    job_name: str
    search_raw_items: Optional[List[dict]]
    skill_list: List[str]
    status: str
    search_round: int
    search_query: str
    next_node: Optional[str]
    task: object  # Task 实例，用于取消检查
