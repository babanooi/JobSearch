# JobSearch — Multi-Agent Job Skill Analysis System

An enterprise-grade multi-agent AI system that analyzes job postings from the web, extracts technical skill requirements, and provides ranked skill insights via REST API and web UI.

## Features

- **Multi-Agent Workflow** — Specialized AI agents (Search, Extract, Evaluate) orchestrated through a LangGraph state machine
- **Intelligent Search** — Searches job boards (targeting zhipin.com) for real-time job postings
- **Iterative Collection** — Evaluates result quality and performs additional targeted searches up to 10 rounds
- **Skill Extraction** — LLM-powered extraction of technical skill keywords with frequency counting
- **Dual Interface** — FastAPI REST API for programmatic access + Streamlit web UI for interactive use
- **Persistent Storage** — MySQL-backed skill rankings queryable by job title

## Architecture

```
User Input (job title)
       │
       ▼
  normalize_node ──► search_node ──► evaluate_node
                         ▲               │
                         │     SEARCH    │
                         └───────────────┘
                                 │ FINISH
                                 ▼
                           extract_node ──► save_node ──► MySQL
```

The workflow uses **LangGraph** to manage state transitions between agents:

| Node | Agent | Responsibility |
|------|-------|----------------|
| `normalize_node` | LLM | Standardize fuzzy job title into precise search query |
| `search_node` | SearchAgent | Fetch job posting text via Tavily Search API |
| `evaluate_node` | SupervisorAgent | LLM decides: collect more or proceed to extraction |
| `extract_node` | ExtractAgent | Parse text and extract technical skill keywords |
| `save_node` | DBTool | Count frequencies, persist to MySQL |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLM** | DeepSeek V4 Pro (via OpenAI-compatible API) |
| **Orchestration** | LangGraph 0.2 + LangChain 0.3 |
| **Search** | Tavily Search API |
| **API Server** | FastAPI |
| **Web UI** | Streamlit |
| **Database** | MySQL + SQLAlchemy ORM |
| **Config** | Pydantic Settings + python-dotenv |

## Project Structure

```
JobSearch/
├── main.py                  # FastAPI entry point
├── app.py                   # Streamlit UI entry point
├── setting.py               # Configuration loader
├── requirements.txt         # Python dependencies
├── agents/                  # AI agent definitions
│   ├── base_agent.py        # Base LLM agent wrapper
│   ├── search_agent.py      # Web search agent
│   ├── extract_agent.py     # Skill extraction agent
│   ├── supervisor_agent.py  # LLM-based router
│   └── registry.py          # Central agent registry
├── graph/                   # LangGraph workflow
│   ├── state.py             # Shared state definition
│   └── workflow.py          # Graph nodes, edges, routing
├── tools/                   # External service wrappers
│   ├── search_tool.py       # Tavily search API wrapper
│   └── db_tool.py           # Database read/write operations
├── database/                # Data layer
│   └── db.py                # ORM models, session management
└── utils/
    └── logger.py            # Colored console logger
```

## Getting Started

### Prerequisites

- Python 3.10+
- MySQL 8.0+
- DeepSeek API key
- Tavily API key

### Installation

```bash
git clone https://github.com/babanooi/JobSearch.git
cd JobSearch
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
MODEL_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-pro
TAVILY_API_KEY=your_tavily_api_key
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/job_skills
```

### Database Setup

Create a MySQL database named `job_skills`. The `job_skills` table will be auto-created on first run.

### Usage

**Streamlit Web UI:**
```bash
streamlit run app.py
```
Open the browser, enter a job title (e.g., "Python后端", "数据分析师"), and click "开始分析" to run the analysis.

**FastAPI Server:**
```bash
python main.py
```

Endpoints:
- `POST /analyze_job` — Trigger analysis: `{"job_name": "Python后端"}`
- `GET /skill_rank/{job_name}?top_n=10` — Get top N skills for a job

### Demo Scripts

```bash
python demo_function_call.py   # OpenAI-style function calling demo
python demo_react.py           # ReAct (Reasoning + Acting) loop demo
```

## Database Schema

The `job_skills` table stores extracted skill rankings:

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT (PK) | Auto-increment ID |
| `job_name` | VARCHAR(255) | Analyzed job title |
| `skill_name` | VARCHAR(255) | Extracted skill keyword |
| `count` | INT | Frequency across all postings |
| `create_time` | DATETIME | Record creation timestamp |

## How It Works

1. You provide a job title (e.g., "后端开发")
2. The system normalizes it into a search-optimized query
3. It searches zhipin.com for matching job postings via Tavily
4. An LLM evaluator checks if enough data was collected — if not, it performs additional targeted searches
5. Once sufficient, another LLM extracts technical skill keywords from all collected text
6. Skills are counted by frequency and saved to MySQL
7. Results are displayed as ranked bar charts in the Streamlit UI or returned as JSON via the API
