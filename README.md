# JobSearch v2.0 — 多智能体求职对话助手

基于 LangGraph 的智能求职助手，支持自然语言对话。自动搜索招聘信息、分析技能需求、对比市场趋势，具备三层记忆体系和多用户对话隔离。

## 功能特性

### 核心能力
- **对话式交互** — Streamlit Chat UI，自然语言提问即可查询技能排名、触发市场分析
- **智能调度** — ChatSupervisor LLM 自主判断用户意图：分析 / 检索 / 确认
- **三层检索** — MySQL 结构化概览 + BM25 关键词召回 + ChromaDB 语义检索，RRF 重排融合
- **双档模型** — deepseek-v4-pro 负责技能提取和摘要压缩，deepseek-chat 负责对话和决策

### 记忆体系
- **工作记忆** — AgentState 管理单次工作流内节点间共享状态
- **短期对话记忆** — SqliteSaver 持久化对话上下文，超过 20 条消息自动 LLM 摘要压缩
- **长期记忆** — MySQL `conversation_summaries` 跨会话持久化，ChromaDB 存储 JD 知识库

### 工程化
- **全链路追踪** — `core/tracer.py` 记录每次 LLM 调用的节点、耗时、Token 消耗
- **输出校验** — `tools/skill_guard.py` 过滤 LLM 异常输出，别名归一化
- **环境自检** — `python main.py doctor` 一键检查所有外部依赖
- **CLI 入口** — `serve / ui / doctor / analyze / rank` 五个子命令

---

## 架构设计

### 六层分离

```
ui/api (表示层)
   │
graphs/ (工作流层)
   │
agents/ (智能体层)
   │
   ├── memory/ (记忆层)
   ├── tools/  (工具层)
   └── models/ (模型层)
   │
core/ (基础设施层)
```

### 工作流拓扑

```
对话工作流:
  supervise → (analyze | query) → generate_response → END

分析工作流:
  search → store_jd → evaluate → (补搜回环 ≤5轮 | extract → save) → END
```

### 智能体职责

| 智能体 | 模型 | 职责 |
|--------|------|------|
| ChatSupervisor | deepseek-chat | LLM 统一决策：分析 / 检索 / 确认 |
| ChatAgent | deepseek-chat | 自然语言回复生成 |
| SearchAgent | Tavily API | 搜索招聘信息 |
| ExtractAgent | v4-pro | 从 JD 提取技术技能关键词 |

### 三层检索

| 层 | 技术 | 作用 |
|----|------|------|
| 第一层 | MySQL 结构化 | 技能排名概览 |
| 第二层 | BM25 + ChromaDB 向量 | 关键词精确 + 语义模糊双路召回 |
| 第三层 | RRF 重排 | 双路结果融合去重排序 |

---

## 技术栈

| 层 | 技术 |
|----|------|
| LLM | DeepSeek V4 Pro + DeepSeek Chat（ChatOpenAI 兼容） |
| Embedding | Dashscope text-embedding-v4 (1024 维) |
| 编排 | LangGraph 0.2 + LangChain 0.3 |
| 搜索 | Tavily Search API |
| 向量库 | ChromaDB (PersistentClient) |
| 关系数据库 | MySQL + SQLAlchemy ORM |
| API | FastAPI |
| UI | Streamlit (st.chat_input / st.chat_message) |
| 对话记忆 | SqliteSaver (langgraph-checkpoint-sqlite) |
| 配置 | python-dotenv |

---

## 项目结构

```
JobSearch/
├── main.py                     # CLI 统一入口
├── .env                        # 环境变量（不入库）
├── requirements.txt
│
├── core/                       # 基础设施层
│   ├── config.py               # 配置单例
│   ├── logger.py               # 彩色日志
│   └── tracer.py               # 全链路调用追踪
│
├── models/                     # 模型层（纯 ORM）
│   ├── database.py             # Base、engine、SessionLocal
│   ├── job.py                  # JobSkills（含 last_seen_at + total_jds）
│   ├── document.py             # JdDocument、JdChunk
│   └── user.py                 # User、Conversation、Summary
│
├── memory/                     # 记忆层
│   ├── working.py              # ① 工作记忆（AgentState）
│   ├── short_term.py           # ② 短期对话（SqliteSaver + LLM 压缩）
│   └── long_term.py            # ③ 长期记忆（ChromaDB + MySQL + 用户体系）
│
├── tools/                      # 工具层
│   ├── search.py               # Tavily 搜索
│   ├── database.py             # 技能排名 CRUD（UPSERT 策略）
│   ├── jd_store.py             # JD 切分 + embedding + MySQL/ChromaDB 双写
│   ├── embedding.py            # Dashscope embedding 工厂
│   └── skill_guard.py          # LLM 输出校验
│
├── agents/                     # 智能体层
│   ├── base.py                 # 双档 LLM 工厂 (get_utility_llm / get_heavy_llm)
│   ├── search.py               # SearchAgent
│   ├── extract.py              # ExtractAgent
│   ├── chat.py                 # ChatAgent（自然语言回复）
│   ├── supervisor_agent.py     # ChatSupervisor（LLM 调度决策）
│   └── registry.py             # 依赖注入注册中心
│
├── graphs/                     # 工作流层
│   ├── state.py                # AgentState 定义
│   ├── analyze.py              # 岗位分析工作流
│   └── chat.py                 # 对话 Agent 工作流
│
├── ui/                         # 表示层
│   └── streamlit_app.py        # Streamlit Chat UI（多用户隔离）
│
├── api/                        # 表示层
│   └── fastapi_app.py          # FastAPI REST API
│
└── data/                       # 运行时数据（不入库）
    ├── chroma_db/              # ChromaDB 向量库
    ├── checkpoints.db          # SqliteSaver 对话记忆
    └── trace.jsonl             # 全链路追踪日志
```

---

## 快速开始

### 环境要求

- Python 3.10+
- MySQL 8.0+
- DeepSeek API key
- Tavily API key
- Dashscope API key（embedding）

### 安装

```bash
git clone https://github.com/babanooi/JobSearch.git
cd JobSearch
pip install -r requirements.txt
```

### 配置

```env
# .env
DEEPSEEK_API_KEY=你的key
MODEL_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-pro
UTILITY_MODEL_NAME=deepseek-chat
TAVILY_API_KEY=你的key
DASHSCOPE_API_KEY=你的key
EMBEDDING_MODEL_NAME=text-embedding-v4
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/job_skills
```

### 数据库

创建 MySQL 数据库 `job_skills`，所有表在首次运行时自动创建。

### 使用

**环境自检：**
```bash
python main.py doctor
```

**启动对话助手（推荐）：**
```bash
python main.py ui
```

**启动 FastAPI：**
```bash
python main.py serve
```

**命令行分析：**
```bash
python main.py analyze "Python后端"
python main.py rank "Python后端" --top 10
```

---

## 数据库表

| 表 | 说明 |
|----|------|
| `job_skills` | 技能排名（含 last_seen_at + total_jds，UPSERT 策略） |
| `jd_documents` | JD 原文 + 元数据（SHA256 去重） |
| `jd_chunks` | JD 文本块 + ChromaDB 关联 |
| `users` | 用户表 |
| `conversations` | 对话关联表（user_id → thread_id） |
| `conversation_summaries` | 压缩摘要持久化 |

---

## 对话交互示例

```
用户: Python后端需要什么技能？
助手: **Python后端** 技能 Top5:
      1. FastAPI (出现 12 次, 样本 15 条 JD, 占比 80%)
      2. Docker (出现 10 次)
      3. MySQL (出现 8 次)
      ...

用户: 帮我分析一下Go开发
助手: 正在为你分析「Go开发」的最新招聘技能需求...
      **Go开发** 最新技能需求 Top10:
      1. Go (出现 15 次)
      2. Gin (出现 8 次)
      ...

用户: 之前分析过哪些岗位？
助手: 已分析岗位: Python后端、Java开发、Go开发
```
