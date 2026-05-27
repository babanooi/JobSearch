# JobLab v3.1 — AI 求职技能情报平台

基于 LangGraph 的多智能体 AI 求职助手。自然语言对话即可自动搜索招聘信息、分析技能需求、提供溯源链接，具备三层记忆体系、混合检索、幻觉防御和双层归一化。

## 功能特性

### 核心能力
- **对话式交互** — 暗夜星图 SPA 前端 + FastAPI，自然语言提问即可查询技能排名、触发市场分析、获取招聘链接
- **ChatAgent 统一决策** — 一次 LLM 调用同时完成"理解意图 + 生成回复 + 输出动作标记"，`[SEARCH:]` / `[ANALYZE:]` / `[RESEARCH:]` 标记路由
- **三层检索** — MySQL 结构化查询 + BM25 中文 2-gram 关键词召回 + ChromaDB 语义向量检索，RRF (k=60) 重排融合
- **双档模型策略** — deepseek-v4-pro 负责技能提取和摘要压缩，deepseek-chat 负责对话/分类/路由/反思，降低成本

### 记忆体系
- **工作记忆** — AgentState 管理单次工作流内节点间共享状态
- **短期对话记忆** — SqliteSaver 持久化对话上下文，超过 20 条消息自动 LLM 滑动窗口压缩（先过滤闲聊，再结构化摘要 ≤200 字）
- **长期记忆** — MySQL `conversation_summaries` 跨会话恢复 + ChromaDB 存储 JD 知识库 + BM25 倒排索引

### 幻觉防御（5 层）
| 层 | 位置 | 机制 |
|------|------|------|
| 入库去重 | `store_jd_node` | SHA256 文本哈希，同内容不重复入库 |
| DB 交叉校验 | `skill_reflect_node` | MySQL 已有技能库白名单，已知技能直接放行 |
| 反思过滤 | `skill_reflect_node` | LLM 只审查未知词，保留技术技能，剔除软技能/公司名 |
| 全文实体溯源 | `verify_citations()` | 归一化实体提取 + 与 knowledge 交叉验证，未溯源标 ~~删除线~~ |
| 无数据兜底 | `chat_node` | 检测技术实体声明但无 knowledge 时追加警告 |

### 溯源增强
- knowledge 条目 `[N]` 编号 + `source_index` 元数据（type/job/company/url）
- ChromaDB → LLM → 用户，URL 全程透传
- SYSTEM_PROMPT 要求引用来源编号 `[N]` 和不确定标注 `[?]`

### 双层归一化（v3.1 新增）
- **岗位名归一化**：`JOB_ALIASES` 别名表 + `normalize_job_name()`，写入口读入口全覆盖，消除"Python后端"6 个变体
- **技能名语义归一化**：embedding 余弦相似度 ≥0.85 自动匹配已有 312 个标准技能名，变体自动标准化

### 工程化
- **全链路追踪** — `core/tracer.py` 记录每次 LLM 调用的节点、耗时、Token 消耗
- **依赖注入** — `agents/registry.py` 统一管理组件生命周期，模块低耦合
- **数据迁移** — `scripts/merge_duplicate_jobs.py` 支持 `--dry-run` / `--execute`
- **环境自检** — `python main.py doctor` 一键检查所有外部依赖

---

## 架构设计

### 六层分离

```
ui/ + api/  (表示层)
     │
graphs/     (工作流层)
     │
agents/     (智能体层)
     │
     ├── memory/  (记忆层)
     ├── tools/   (工具层)
     └── models/  (模型层)
     │
core/       (基础设施层)
```

### 工作流拓扑

```
chat 工作流（总入口）:
  chat_node → [SEARCH:] → rag_query → chat_node（带回 knowledge）
           → [ANALYZE:] → trigger_analyze → analyze 工作流 → chat_node
           → [RESEARCH:] → research 工作流 → chat_node
           → 无标记 → END

analyze 工作流:
  search → store_jd → evaluate（≤5轮回环）→ extract（并行）→ skill_reflect → save → END

research 工作流:
  plan → parallel_execute（4 workers）→ synthesize → reflect（≤1轮补搜）→ END
```

### 智能体职责

| 智能体 | 模型 | 职责 |
|--------|------|------|
| ChatAgent | deepseek-chat | 意图识别 + 对话回复 + 标记解析 + 溯源校验 |
| SearchAgent | Tavily API | 搜索 JD 原文，不做解析 |
| ExtractAgent | v4-pro | 从 JD 文本提取技能关键词（并行分批） |

### 检索策略

```
[SEARCH:关键词]
      │
      ├── 链路 1: MySQL 语义匹配岗位 → 结构化查询技能排名（概览）
      │
      └── 链路 2: BM25 关键词 ─┐
                 ChromaDB 向量 ─┤ RRF (k=60) → Top-3 JD 片段 + URL（证据）
               
      两路结果编号 [N] 拼合，送入 ChatAgent 生成带引用来源的回答
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| LLM | DeepSeek V4 Pro + DeepSeek Chat（OpenAI 兼容） |
| Embedding | Dashscope text-embedding-v4 (1024 维) |
| 编排 | LangGraph StateGraph + SqliteSaver |
| 搜索 | Tavily Search API |
| 向量库 | ChromaDB (PersistentClient, HNSW cosine) |
| 关系数据库 | MySQL + SQLAlchemy ORM (charset=utf8mb4) |
| 关键词检索 | 自研 SimpleBM25（中文 2-gram 分词，零外部依赖） |
| API | FastAPI |
| 前端 | Vanilla JS SPA（Canvas 星空粒子、四视图切换、雷达图手绘） |
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
│   └── tracer.py               # 全链路调用追踪（JSONL）
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
│   └── long_term.py            # ③ 长期记忆（ChromaDB + MySQL + BM25 + RRF）
│
├── tools/                      # 工具层
│   ├── search.py               # Tavily 搜索
│   ├── database.py             # 技能排名 CRUD（UPSERT 策略 + 归一化）
│   ├── jd_store.py             # JD 切分 + embedding + MySQL/ChromaDB 双写（SHA256 去重）
│   ├── embedding.py            # Dashscope embedding 工厂
│   └── skill_guard.py          # 技能/岗位名归一化 + 输出校验 + 语义匹配
│
├── agents/                     # 智能体层
│   ├── base.py                 # 双档 LLM 工厂 (get_utility_llm / get_heavy_llm)
│   ├── search.py               # SearchAgent
│   ├── extract.py              # ExtractAgent
│   ├── chat.py                 # ChatAgent（标记解析 + 溯源校验 + 实体归一化）
│   ├── supervisor_agent.py     # ChatSupervisor（已废弃，被 ChatAgent 标记替代）
│   └── registry.py             # 依赖注入注册中心
│
├── graphs/                     # 工作流层
│   ├── state.py                # AgentState 定义
│   ├── analyze.py              # 岗位分析工作流（6 节点 + 条件回环）
│   ├── chat.py                 # 对话工作流（标记路由 + 3 路分发）
│   └── research.py             # 研究工作流（并行 + 反思 + 补搜回路）
│
├── ui/static/                  # 前端（暗夜星图 SPA）
│   ├── index.html              # SPA 入口
│   ├── app.js                  # 四视图切换 + 对话 + 雷达图（Canvas）+ 研究
│   └── style.css               # Dark Constellation 主题
│
├── api/                        # API 层
│   └── fastapi_app.py          # 7 个 REST 端点 + 静态文件托管
│
├── scripts/                    # 运维脚本
│   └── merge_duplicate_jobs.py # 岗位名重复合并迁移
│
└── data/                       # 运行时数据（不入库）
    ├── chroma_db/              # ChromaDB 向量库
    ├── checkpoints.db          # SqliteSaver 对话记忆
    └── trace.jsonl             # 全链路追踪日志
```

---

## 数据库表

| 表 | 说明 |
|----|------|
| `job_skills` | 技能排名（含 last_seen_at + total_jds，UPSERT 策略） |
| `jd_documents` | JD 原文 + 元数据（SHA256 去重，source_url 溯源） |
| `jd_chunks` | JD 文本块 + ChromaDB 关联（BM25 索引数据源） |
| `users` | 用户表 |
| `conversations` | 对话关联表（user_id → thread_id） |
| `conversation_summaries` | 压缩摘要持久化（跨会话恢复） |

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
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/job_skills?charset=utf8mb4
```

### 使用

**环境自检：**
```bash
python main.py doctor
```

**启动服务：**
```bash
python main.py serve
# 访问 http://localhost:8000
```

**命令行分析：**
```bash
python main.py analyze "Python后端"
python main.py rank "Python后端" --top 10
```

**数据迁移（合并重复岗位名）：**
```bash
python scripts/merge_duplicate_jobs.py --dry-run   # 预览
python scripts/merge_duplicate_jobs.py --execute    # 执行
```

---

## 版本历史

| 版本 | 亮点 |
|------|------|
| v3.1 | 岗位名+技能名双层归一化，数据迁移脚本，消除数据孤岛 |
| v3.0 | 幻觉防御体系（5层）+ 溯源增强 + 前端 UX 全面修复 |
| v2.0 | 六层架构重构，三层记忆体系，ChatAgent 统一决策，三层双路检索，多用户隔离 |
| v1.0 | 基础岗位分析，技能提取与排名 |
