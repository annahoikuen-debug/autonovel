"""LLM アダプタパッケージ。

統合先: src/llm/adapters/
実体は base.py, factory.py, gemini.py, mock.py, openai.py, ollama.py,
claude.py, vllm.py, tracked.py, failover.py, retry.py, prompts.py,
prompt_cache.py にある。
"""

from __future__ import annotations

from src.llm.adapters.base import BaseLLMAdapter  # noqa: F401
from src.llm.adapters.factory import get_llm_adapter  # noqa: F401
from src.llm.adapters.gemini import GeminiAdapter  # noqa: F401
from src.llm.adapters.mock import MockLLMAdapter  # noqa: F401
from src.llm.adapters.openai import OpenAIAdapter  # noqa: F401

__all__ = [
    "BaseLLMAdapter",
    "GeminiAdapter",
    "MockLLMAdapter",
    "OpenAIAdapter",
    "get_llm_adapter",
]
