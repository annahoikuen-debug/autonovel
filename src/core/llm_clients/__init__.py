"""低レベル LLM 通信クライアント。

``GeminiApiClient`` は ``google.genai`` SDK をトップレベルで import するため、
パッケージ __init__ でそれを読み込むと API サーバーの起動が数秒遅くなる。
そこで公開シンボルは PEP 562 のモジュール ``__getattr__`` で遅延公開する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "BaseLLMClient": ("src.core.llm_clients.base", "BaseLLMClient"),
    "GeminiApiClient": ("src.core.llm_clients.gemini", "GeminiApiClient"),
    "OpenAIApiClient": ("src.core.llm_clients.openai", "OpenAIApiClient"),
}

if TYPE_CHECKING:  # pragma: no cover - 型チェックのみ
    from src.core.llm_clients.base import BaseLLMClient
    from src.core.llm_clients.gemini import GeminiApiClient
    from src.core.llm_clients.openai import OpenAIApiClient


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module_path, attr = target
    value = getattr(importlib.import_module(module_path), attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    "BaseLLMClient",
    "GeminiApiClient",
    "OpenAIApiClient",
]
