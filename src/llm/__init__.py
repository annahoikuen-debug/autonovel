"""LLM 統合パッケージ（公式エントリポイント）。

LLM 関連モジュールはこのパッケージに統合されている。
新規コードでは以下のように import してください:

    from src.llm import (
        LLMCircuitBreaker,
        ResilientLLMGateway,
        LLMProvider,
        LLMResponse,
    )

【移行ガイド】
  旧 import                           → 新 import
  from src.core.llm import LLMCircuitBreaker   → from src.llm import LLMCircuitBreaker
  from src.llm.circuit_breaker import ...      → from src.llm import ...（維持）
"""

from __future__ import annotations

from src.llm.circuit_breaker import (  # noqa: F401
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitState,
    LLMCircuitBreaker,
    ProviderHealthState,
)
from src.llm.resilient_gateway import ResilientLLMGateway  # noqa: F401
from src.llm.base import LLMProvider, LLMResponse  # noqa: F401

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenException",
    "CircuitState",
    "LLMCircuitBreaker",
    "ProviderHealthState",
    "ResilientLLMGateway",
    "LLMProvider",
    "LLMResponse",
]
