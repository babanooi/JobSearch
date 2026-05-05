from agents.base_agent import BaseAgent

class SupervisorAgent(BaseAgent):
    """
    【主管调度Agent — 企业级核心】
    职责：
    1. 读取当前全局状态
    2. LLM自主判断：下一步应该执行哪个节点
    3. 动态路由：search / extract / save / end
    4. 控制整个多Agent流程终止条件
    """
    def run(self, state: dict) -> str:
        job_name = state.get("job_name")
        has_search = bool(state.get("search_raw_content"))
        has_skill = bool(state.get("skill_list"))

        prompt = f"""
你是多智能体系统的主管调度员，根据当前流程状态，只返回**唯一节点名称**。

可选节点：
1. search_node：未获取招聘内容时执行
2. extract_node：已有搜索内容、未提取技能时执行
3. save_node：已有技能列表、未入库时执行
4. end：全部流程完成，结束任务

当前状态：
岗位名称：{job_name}
是否已搜索内容：{has_search}
是否已提取技能：{has_skill}

规则：
- 严格只返回节点单词，不要解释、不要标点
"""
        decision = self.llm.invoke(prompt).content.strip()
        return decision

supervisor_agent = SupervisorAgent()