from langchain_openai import ChatOpenAI
from core.config import settings

# 轻量模型（对话/分类/标准化），deepseek-chat
_utility_llm: ChatOpenAI | None = None

# 重量模型（技能提取/摘要压缩），deepseek-v4-pro
_heavy_llm: ChatOpenAI | None = None


def get_utility_llm() -> ChatOpenAI:
    global _utility_llm
    if _utility_llm is None:
        _utility_llm = ChatOpenAI(
            model=settings.UTILITY_MODEL_NAME,
            openai_api_key=settings.DEEPSEEK_API_KEY,
            openai_api_base=settings.MODEL_BASE_URL,
            temperature=0.1,
            max_tokens=512,
        )
    return _utility_llm


def get_heavy_llm() -> ChatOpenAI:
    global _heavy_llm
    if _heavy_llm is None:
        _heavy_llm = ChatOpenAI(
            model=settings.MODEL_NAME,
            openai_api_key=settings.DEEPSEEK_API_KEY,
            openai_api_base=settings.MODEL_BASE_URL,
            temperature=0.1,
        )
    return _heavy_llm


class BaseAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.MODEL_NAME,
            openai_api_key=settings.DEEPSEEK_API_KEY,
            openai_api_base=settings.MODEL_BASE_URL,
            temperature=0.1,
        )

    def run(self, input_content: str) -> str:
        raise NotImplementedError("子类必须实现 run 方法")
