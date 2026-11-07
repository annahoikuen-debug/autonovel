"""LLM サービスパッケージ（後方互換 shim）。

実体は src/llm/adapters/ に移設済み。
サブモジュール（factory, gemini_adapter, mock_adapter 等）への
直接参照も PEP 562 の __getattr__ で新パスにリダイレクトする。
"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.llm.__init__ is deprecated; use src.llm.adapters instead",
    DeprecationWarning,
    stacklevel=2,
)

import importlib
import sys

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

#: サブモジュール名 -> 新パス のマッピング
#: ``from src.services.llm.factory import get_llm_adapter`` 等の
#: サブモジュール直接参照を新パスにリダイレクトする。
_LAZY_MODULE_EXPORTS: dict[str, str] = {
    "base": "src.llm.adapters.base",
    "factory": "src.llm.adapters.factory",
    "gemini_adapter": "src.llm.adapters.gemini",
    "mock_adapter": "src.llm.adapters.mock",
    "openai_adapter": "src.llm.adapters.openai",
    "ollama_adapter": "src.llm.adapters.ollama",
    "claude_adapter": "src.llm.adapters.claude",
    "vllm_adapter": "src.llm.adapters.vllm",
    "tracked_adapter": "src.llm.adapters.tracked",
    "provider_failover": "src.llm.adapters.failover",
    "retry": "src.llm.adapters.retry",
    "prompts": "src.llm.adapters.prompts",
    "prompt_cache_builder": "src.llm.adapters.prompt_cache",
    "circuit_breaker": "src.llm.circuit_breaker",
}


def __getattr__(name: str):
    """サブモジュールを新パスに遅延リダイレクトする (PEP 562)。"""
    target = _LAZY_MODULE_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(target)
    # キャッシュして次回以降は __getattr__ を経由しない
    sys.modules[f"{__name__}.{name}"] = module
    return module
