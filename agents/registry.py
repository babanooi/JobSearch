"""多 Agent 组件注册中心 —— 依赖注入，隔离各层"""
import chromadb
from pathlib import Path

from agents.search import SearchAgent
from agents.extract import ExtractAgent
from agents.chat import ChatAgent
from tools.search import JobSearchTool
from tools.database import DBTool
from tools.jd_store import JDStore
from tools.embedding import create_embeddings
from models.database import SessionLocal
from core.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent


class Registry:
    def __init__(self):
        # 工具层
        self.search_tool = JobSearchTool()
        self.db_tool = DBTool()

        # 智能体层
        self.search_agent = SearchAgent(search_tool=self.search_tool)
        self.extract_agent = ExtractAgent()
        self.chat_agent = ChatAgent()

        # JD 知识库存储
        embeddings = create_embeddings()
        chroma_client = chromadb.PersistentClient(
            path=str(BASE_DIR / "data" / "chroma_db")
        )
        self.jd_store = JDStore(
            embeddings=embeddings,
            db_session_factory=SessionLocal,
            chroma_client=chroma_client,
        )
        self.embeddings = embeddings


registry = Registry()
