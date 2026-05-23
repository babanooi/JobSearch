"""求职助手 Chat UI —— 多用户对话隔离 + 历史对话列表"""
import streamlit as st
from dotenv import load_dotenv

load_dotenv(override=True)

import models  # 触发所有 ORM 模型注册（User/Conversation/Summary）
from models.database import init_database
from agents.registry import registry
from graphs.chat import chat_agent_graph, new_thread_id
from memory.long_term import (
    query_skill_rank, list_analyzed_jobs,
    get_or_create_user, list_user_conversations,
)

st.set_page_config(page_title="求职助手", layout="wide")

init_database()

# ── 用户标识 ──
if "username" not in st.session_state:
    st.session_state.username = f"用户_{new_thread_id()[:8]}"
if "user_id" not in st.session_state:
    st.session_state.user_id = get_or_create_user(st.session_state.username)
if "thread_id" not in st.session_state:
    st.session_state.thread_id = new_thread_id()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "summary" not in st.session_state:
    st.session_state.summary = ""


def switch_conversation(tid: str):
    st.session_state.thread_id = tid
    st.session_state.messages = []
    st.session_state.summary = ""
    st.rerun()


# ── 侧边栏 ──
with st.sidebar:
    st.title("求职助手")
    st.caption(f"当前用户: {st.session_state.username}")

    if st.button("+ 新对话", use_container_width=True):
        st.session_state.thread_id = new_thread_id()
        st.session_state.messages = []
        st.session_state.summary = ""
        st.rerun()

    st.divider()
    st.subheader("历史对话")

    try:
        convs = list_user_conversations(st.session_state.user_id)
        for c in convs:
            label = f"{c['title'][:30]} ({c['updated_at']})"
            is_current = c["thread_id"] == st.session_state.thread_id
            if st.button(
                ("● " if is_current else "  ") + label,
                key=c["thread_id"],
                use_container_width=True,
                help=f"恢复到 {c['updated_at']} 的对话",
            ):
                switch_conversation(c["thread_id"])
    except Exception:
        st.caption("暂无历史对话")

    st.divider()
    st.caption("已分析岗位")
    try:
        jobs = list_analyzed_jobs()
        for j in jobs:
            st.write(f"- {j}")
    except Exception:
        st.caption("暂无")

# ── 主界面 ──
st.title("求职技能分析助手")
st.caption("问我任何岗位的技能需求，或让我帮你分析最新招聘市场")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if user_input := st.chat_input("例如：Python后端需要什么技能？"):
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("思考中..."):
            result = chat_agent_graph.invoke(
                {
                    "thread_id": st.session_state.thread_id,
                    "user_id": st.session_state.user_id,
                    "messages": st.session_state.messages,
                    "user_input": user_input,
                    "summary": st.session_state.summary,
                    "knowledge": [],
                    "response": "",
                },
                config={"configurable": {"thread_id": st.session_state.thread_id}},
            )
            response = result.get("response", "抱歉，处理出错")
            st.write(response)

            st.session_state.messages = result.get("messages", [])
            st.session_state.summary = result.get("summary", "")
