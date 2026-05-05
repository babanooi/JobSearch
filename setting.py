import os
from pathlib import Path

from dotenv import load_dotenv

# 强制加载.env文件（关键：写在最前面，并且指定路径）
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path, override=True)

class Settings:
    # 注意：这里变量名必须和 .env 里的键完全一致
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    MODEL_BASE_URL: str = os.getenv("MODEL_BASE_URL", "")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "")
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    # MySQL 连接字符串格式：mysql+aiomysql://用户:密码@主机:端口/数据库名
    DATABASE_URL: str = os.getenv( "DATABASE_URL")

# 全局单例
settings = Settings()



