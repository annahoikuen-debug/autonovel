"""低レベル LLM 通信クライアント（後方互換 shim）。

実体は src/llm/clients/ に移設済み。
"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.core.llm_clients.__init__ is deprecated; use src.llm.clients instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.llm.clients.base import BaseLLMClient  # noqa: F401
from src.llm.clients.gemini import GeminiApiClient  # noqa: F401
from src.llm.clients.openai import OpenAIApiClient  # noqa: F401

__all__ = ["BaseLLMClient", "GeminiApiClient", "OpenAIApiClient"]
