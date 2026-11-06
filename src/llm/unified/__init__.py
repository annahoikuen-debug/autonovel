"""LLM 統合インターフェースパッケージ。

統合先: src/llm/unified/
実体は interface.py, types.py, factory.py, adapters/ にある。
"""

from __future__ import annotations

from src.llm.unified.interface import IUnifiedLLMClient, with_metrics  # noqa: F401
from src.llm.unified.types import LLMRequest, LLMResponse, LLMUsage, StreamChunk  # noqa: F401
from src.llm.unified.factory import create_unified_llm_client  # noqa: F401
from src.llm.unified.adapters.claude import ClaudeUnifiedClient  # noqa: F401
from src.llm.unified.adapters.gemini import GeminiUnifiedClient  # noqa: F401
from src.llm.unified.adapters.mock import UnifiedMockLLMClient  # noqa: F401
from src.llm.unified.adapters.ollama import OllamaUnifiedClient  # noqa: F401
from src.llm.unified.adapters.openai import OpenAIUnifiedClient  # noqa: F401

__all__ = [
    "IUnifiedLLMClient",
    "LLMRequest",
    "LLMResponse",
    "LLMUsage",
    "StreamChunk",
    "create_unified_llm_client",
    "with_metrics",
    "ClaudeUnifiedClient",
    "GeminiUnifiedClient",
    "UnifiedMockLLMClient",
    "OllamaUnifiedClient",
    "OpenAIUnifiedClient",
]
