import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path, override=True)


class Settings:
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    MODEL_BASE_URL: str = os.getenv("MODEL_BASE_URL", "")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "")
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    ANYSEARCH_API_KEY: str = os.getenv("ANYSEARCH_API_KEY", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v4")
    # 摘要压缩等辅助任务用轻量模型，节省成本
    UTILITY_MODEL_NAME: str = os.getenv("UTILITY_MODEL_NAME", "deepseek-chat")


settings = Settings()
