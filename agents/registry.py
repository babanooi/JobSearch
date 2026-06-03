"""多 Agent 组件注册中心 —— 依赖注入，隔离各层。外部服务懒加载。"""
from pathlib import Path

from agents.search import SearchAgent
from agents.extract import ExtractAgent
from agents.chat import ChatAgent
from tools.search import JobSearchTool
from tools.database import DBTool
from core.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent


class Registry:
    def __init__(self):
        # ── 轻量组件：import 即初始化 ──
        self.search_tool = JobSearchTool()
        self.db_tool = DBTool()
        self.search_agent = SearchAgent(search_tool=self.search_tool)
        self.extract_agent = ExtractAgent()
        self.chat_agent = ChatAgent()

        # ── 重量组件：懒加载（首次访问时才初始化）──
        self._embeddings = None
        self._jd_store = None

    @property
    def embeddings(self):
        """懒加载 embedding 实例（首次访问时创建）"""
        if self._embeddings is None:
            from tools.embedding import create_embeddings
            self._embeddings = create_embeddings()
        return self._embeddings

    @property
    def jd_store(self):
        """懒加载 JDStore（首次访问时创建 ChromaDB 客户端 + embedding）"""
        if self._jd_store is None:
            import chromadb
            from tools.jd_store import JDStore
            from models.database import SessionLocal
            chroma_client = chromadb.PersistentClient(
                path=str(BASE_DIR / "data" / "chroma_db")
            )
            self._jd_store = JDStore(
                embeddings=self.embeddings,
                db_session_factory=SessionLocal,
                chroma_client=chroma_client,
            )
        return self._jd_store

    @property
    def llm(self):
        """快捷访问 LLM 实例（用于摘要压缩等辅助任务）"""
        return self.extract_agent.llm


registry = Registry()
