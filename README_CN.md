# JobSearch — 多智能体职位技能分析系统

一个企业级多智能体AI系统，从网络上分析职位招聘信息，提取技术技能要求，并通过 REST API 和 Web UI 提供技能排名洞察。

## 功能特性

- **多智能体工作流** — 通过 LangGraph 状态机编排的专用 AI 智能体（搜索、提取、评估）
- **智能搜索** — 搜索招聘网站（主要针对 zhipin.com）获取实时职位信息
- **迭代采集** — 评估结果质量，最多执行 10 轮定向补充搜索
- **技能提取** — LLM 驱动的技术技能关键词提取与频率统计
- **双界面** — FastAPI REST API 供程序调用 + Streamlit Web UI 供交互式使用
- **持久化存储** — MySQL 存储技能排名，可按职位名称查询

## 架构设计

```
用户输入（职位名称）
       │
       ▼
  normalize_node ──► search_node ──► evaluate_node
                         ▲               │
                         │   再次搜索    │
                         └───────────────┘
                                 │ 结束搜索
                                 ▼
                           extract_node ──► save_node ──► MySQL
```

工作流使用 **LangGraph** 管理智能体之间的状态转换：

| 节点 | 智能体 | 职责 |
|------|--------|------|
| `normalize_node` | LLM | 将模糊的职位名称标准化为精确的搜索关键词 |
| `search_node` | SearchAgent | 通过 Tavily 搜索 API 获取职位描述文本 |
| `evaluate_node` | SupervisorAgent | LLM 决策：继续采集还是进入提取阶段 |
| `extract_node` | ExtractAgent | 解析文本并提取技术技能关键词 |
| `save_node` | DBTool | 统计频率，持久化到 MySQL |

## 技术栈

| 层级 | 技术 |
|------|------|
| **LLM** | DeepSeek V4 Pro（通过 OpenAI 兼容 API） |
| **编排** | LangGraph 0.2 + LangChain 0.3 |
| **搜索** | Tavily Search API |
| **API 服务** | FastAPI |
| **Web UI** | Streamlit |
| **数据库** | MySQL + SQLAlchemy ORM |
| **配置** | Pydantic Settings + python-dotenv |

## 项目结构

```
JobSearch/
├── main.py                  # FastAPI 入口
├── app.py                   # Streamlit UI 入口
├── setting.py               # 配置加载器
├── requirements.txt         # Python 依赖
├── agents/                  # AI 智能体定义
│   ├── base_agent.py        # LLM 智能体基类
│   ├── search_agent.py      # 网页搜索智能体
│   ├── extract_agent.py     # 技能提取智能体
│   ├── supervisor_agent.py  # LLM 路由器
│   └── registry.py          # 智能体注册中心
├── graph/                   # LangGraph 工作流
│   ├── state.py             # 共享状态定义
│   └── workflow.py          # 图节点、边、路由
├── tools/                   # 外部服务封装
│   ├── search_tool.py       # Tavily 搜索 API 封装
│   └── db_tool.py           # 数据库读写操作
├── database/                # 数据层
│   └── db.py                # ORM 模型、会话管理
└── utils/
    └── logger.py            # 彩色控制台日志
```

## 快速开始

### 环境要求

- Python 3.10+
- MySQL 8.0+
- DeepSeek API 密钥
- Tavily API 密钥

### 安装

```bash
git clone https://github.com/babanooi/JobSearch.git
cd JobSearch
pip install -r requirements.txt
```

### 配置

在项目根目录创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=你的_deepseek_api_key
MODEL_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-pro
TAVILY_API_KEY=你的_tavily_api_key
DATABASE_URL=mysql+pymysql://用户名:密码@localhost:3306/job_skills
```

### 数据库设置

创建一个名为 `job_skills` 的 MySQL 数据库。`job_skills` 表将在首次运行时自动创建。

### 使用方式

**Streamlit Web UI：**
```bash
streamlit run app.py
```
在浏览器中打开，输入职位名称（如"Python后端"、"数据分析师"），点击"开始分析"即可运行分析。

**FastAPI 服务：**
```bash
python main.py
```

接口端点：
- `POST /analyze_job` — 触发分析：`{"job_name": "Python后端"}`
- `GET /skill_rank/{job_name}?top_n=10` — 获取某职位的前 N 项技能

### 演示脚本

```bash
python demo_function_call.py   # OpenAI 风格函数调用演示
python demo_react.py           # ReAct（推理+行动）循环演示
```

## 数据库结构

`job_skills` 表存储提取的技能排名：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INT（主键） | 自增 ID |
| `job_name` | VARCHAR(255) | 被分析的职位名称 |
| `skill_name` | VARCHAR(255) | 提取的技能关键词 |
| `count` | INT | 在所有职位中出现频次 |
| `create_time` | DATETIME | 记录创建时间 |

## 工作原理

1. 你提供一个职位名称（如"后端开发"）
2. 系统将其标准化为适合搜索的查询关键词
3. 通过 Tavily 在 zhipin.com 上搜索匹配的职位信息
4. LLM 评估器检查是否采集到足够数据 — 如果不够，则执行定向补充搜索
5. 收集充分后，另一个 LLM 从所有文本中提取技术技能关键词
6. 技能按出现频率统计并保存到 MySQL
7. 结果在 Streamlit UI 中以排名柱状图展示，或通过 API 以 JSON 格式返回
