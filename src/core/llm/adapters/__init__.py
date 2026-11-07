"""LLM 統合アダプタ（後方互換 shim）。

実体は src/llm/unified/adapters/ に移設済み。
"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.core.llm.adapters.__init__ is deprecated; use src.llm.unified.adapters instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.llm.unified.adapters.claude import ClaudeUnifiedClient  # noqa: F401
from src.llm.unified.adapters.gemini import GeminiUnifiedClient  # noqa: F401
from src.llm.unified.adapters.mock import UnifiedMockLLMClient  # noqa: F401
from src.llm.unified.adapters.ollama import OllamaUnifiedClient  # noqa: F401
from src.llm.unified.adapters.openai import OpenAIUnifiedClient  # noqa: F401

__all__ = [
    "ClaudeUnifiedClient",
    "GeminiUnifiedClient",
    "UnifiedMockLLMClient",
    "OllamaUnifiedClient",
    "OpenAIUnifiedClient",
]
