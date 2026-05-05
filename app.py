import time
import uuid

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env", override=True)

from database.db import init_database
from agents.registry import registry

st.set_page_config(page_title="岗位技能分析系统", layout="wide")

# ── 初始化 ──
if "history" not in st.session_state:
    st.session_state.history = []


# ── 侧边栏 ──
with st.sidebar:
    st.title("📋 分析历史")
    if st.button("🔄 刷新"):
        st.rerun()

    for item in reversed(st.session_state.history[-20:]):
        with st.expander(f"{item['job']} — {item['elapsed']}", expanded=False):
            for s in item["skills"]:
                st.write(f"`{s['skill']}` ×{s['count']}")

# ── 主页面 ──
st.title("🔍 企业级多 Agent 岗位技能分析系统")
st.caption("输入岗位名称 → 多 Agent 协作搜索/提取/统计 → 技能热度排行")

col1, col2, col3 = st.columns([4, 1, 1])
with col1:
    job_name = st.text_input("岗位名称", placeholder="例如: Python后端开发工程师")
with col2:
    st.write("")
    st.write("")
    quick_jobs = st.selectbox(
        "快速选择", ["", "Python后端", "数据分析师", "前端开发", "AI产品经理"]
    )
    if quick_jobs and not job_name:
        job_name = quick_jobs
with col3:
    st.write("")
    st.write("")
    analyze_clicked = st.button("🚀 开始分析", type="primary", use_container_width=True)

# ── 执行分析 ──
if analyze_clicked and job_name.strip():
    t0 = time.time()
    thread_id = str(uuid.uuid4())

    status_container = st.status(f"正在分析: {job_name}", expanded=True)

    try:
        # 初始化数据库
        init_database()

        # 运行工作流
        with status_container:
            st.write("⏳ 工作流启动...")
            result = registry.search_agent.run.__self__  # just placeholder

        # 实际调用
        from graph.workflow import agent_graph

        result = agent_graph.invoke(
            {"job_name": job_name.strip(), "status": "开始执行"},
            config={"configurable": {"thread_id": thread_id}},
        )

        elapsed = time.time() - t0

        # 从数据库获取排行
        db = registry.db_tool
        skills = db.get_skill_rank(job_name.strip(), top_n=15)

        status_container.update(label=f"分析完成: {job_name}", state="complete", expanded=False)

        # ── 结果展示 ──
        st.success(f"分析完成 · 耗时 {elapsed:.1f}s · thread_id: `{thread_id}`")

        c1, c2 = st.columns([3, 2])

        with c1:
            st.subheader("📊 技能热度排行")
            if skills:
                df = pd.DataFrame(skills)
                df.columns = ["技能", "出现次数"]
                st.bar_chart(df.set_index("技能"), use_container_width=True)
            else:
                st.info("暂无技能数据")

        with c2:
            st.subheader("📋 技能列表")
            if skills:
                for s in skills:
                    st.metric(s["skill"], f"出现 {s['count']} 次")
            else:
                st.info("暂无技能数据")

        # 记录历史
        st.session_state.history.append({
            "job": job_name.strip(),
            "elapsed": f"{elapsed:.1f}s",
            "skills": skills,
            "thread_id": thread_id,
        })

    except Exception as e:
        status_container.update(label=f"分析失败: {job_name}", state="error")
        st.error(f"工作流执行异常: {e}")
        st.exception(e)

elif analyze_clicked and not job_name.strip():
    st.warning("请输入岗位名称")

# ── 数据库查询 ──
st.divider()
st.subheader("📦 已入库岗位技能查询")

query_col1, query_col2 = st.columns([3, 1])
with query_col1:
    query_job = st.text_input("查询岗位名", key="query_job", placeholder="输入已分析过的岗位名")
with query_col2:
    st.write("")
    st.write("")
    query_clicked = st.button("🔎 查询", use_container_width=True)

if query_clicked and query_job.strip():
    try:
        init_database()
        db = registry.db_tool
        skills = db.get_skill_rank(query_job.strip(), top_n=10)
        if skills:
            df = pd.DataFrame(skills)
            df.columns = ["技能", "出现次数"]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("该岗位暂无数据，请先执行分析")
    except Exception as e:
        st.error(f"查询失败: {e}")
