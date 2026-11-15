from __future__ import annotations

from typing import Any

from src.core.observability import StructuredLogger

logger = StructuredLogger(__name__)


def create_genai_client(api_key: str):
    """Gemini API クライアントを作成する"""
    from google import genai

    return genai.Client(api_key=api_key)


def LLMGateway(llm: Any = None, repo: Any = None, **kwargs: Any):
    """旧 LLMGateway（LLMGenerateResultProxy）の後方互換ファクトリ。

    PLAN_Q3: LLMProviderFactory/LLMGenerateResultProxy は削除済み。
    代替として src.llm.service.LLMService を返す。
    """
    from src.llm.service import LLMService

    return LLMService(llm=llm, repo=repo, **kwargs)


class SemanticCacheManager:
    """意味的キャッシュマネージャ"""

    def __init__(self, vector_store=None):
        self.vector_store = vector_store

    def get(self, key: str):
        try:
            if self.vector_store and hasattr(self.vector_store, "get"):
                return self.vector_store.get(key)
            return None
        except Exception as e:
            logger.warning(f"Cache get failed for key={e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 3600):
        try:
            if self.vector_store and hasattr(self.vector_store, "set"):
                self.vector_store.set(key, value, ttl)
        except Exception as e:
            logger.warning(f"Cache set failed for key={e}")
