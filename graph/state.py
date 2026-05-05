from typing import TypedDict, List, Optional


# 全局工作流状态(字典)
class AgentState(TypedDict):
    # 用户输入
    job_name: str

    # LLM 标准化后的搜索词
    normalized_query: str

    # 搜索Agent产出：多轮收集的招聘信息, 列表
    search_content: List[str]

    # 抽取Agent产出
    skill_list: List[str]

    # 流程状态
    status: str

    # 当前搜索轮数
    search_round: int

    # 本轮搜索关键词
    search_query: str

    #主管agent决策下一步
    next_node: Optional[str]
