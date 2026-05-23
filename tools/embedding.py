"""Embedding 工厂 —— 隔离 provider 差异"""
from langchain_community.embeddings import DashScopeEmbeddings
from core.config import settings


def create_embeddings() -> DashScopeEmbeddings:
    return DashScopeEmbeddings(
        model=settings.EMBEDDING_MODEL_NAME,
        dashscope_api_key=settings.DASHSCOPE_API_KEY,
    )
