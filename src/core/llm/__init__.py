"""
src/core/llm — LLM 統合インターフェース（公式エントリポイント）

このパッケージが LLM 関連クラスの正規の import 先です。

【使い方】
新規コードでは以下のように import してください:

    from src.core.llm import (
        IUnifiedLLMClient,   # LLM クライアントの抽象インターフェース
        LLMRequest,          # リクエストデータクラス
        LLMResponse,         # レスポンスデータクラス
        ResilientLLMGateway, # 耐障害性 LLM ゲートウェイ
        LLMCircuitBreaker,   # サーキットブレーカー
        create_unified_llm_client,  # クライアントファクトリ
    )

【移行ガイド】
  旧 import                           → 新 import
  from src.llm.resilient_gateway import ResilientLLMGateway
                                      → from src.core.llm import ResilientLLMGateway
  from src.llm.circuit_breaker import LLMCircuitBreaker
                                      → from src.core.llm import LLMCircuitBreaker
  from src.core.llm_clients import BaseLLMClient
                                      → from src.core.llm import BaseLLMClient

  src.llm.* の元モジュールは後方互換のため当面維持しますが、
  将来のバージョンで削除予定です。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

# --------------------------------------------------------------------------- #
# 公開インターフェース（新規コードはここから import する）
#
# ここに見えるプロバイダ适配子类は google-genai / openai / anthropic の
# 各SDKをトップレベルで import する。API サーバーは起動時に一度も
# プロバイダを生成しないため、それらを import すると起動が 10 秒以上
# 遅くなる。このため属性アクセスは PEP 562 の __getattr__ で遅延させ、
# 公開 API (``from src.core.llm import X``) はそのまま維持する。
# --------------------------------------------------------------------------- #

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    # 統合抽象インターフェース・型（軽量なので即時 import してよいもの）
    "IUnifiedLLMClient": ("src.core.llm.unified_interface", "IUnifiedLLMClient"),
    "LLMRequest": ("src.core.llm.types", "LLMRequest"),
    "LLMResponse": ("src.core.llm.types", "LLMResponse"),
    "LLMUsage": ("src.core.llm.types", "LLMUsage"),
    "StreamChunk": ("src.core.llm.types", "StreamChunk"),
    # アダプタ群（SDK を/topLevel import するため遅延）
    "GeminiUnifiedClient": ("src.core.llm.adapters.gemini_unified_client", "GeminiUnifiedClient"),
    "OpenAIUnifiedClient": ("src.core.llm.adapters.openai_unified_client", "OpenAIUnifiedClient"),
    "UnifiedMockLLMClient": ("src.core.llm.adapters.mock_unified_client", "UnifiedMockLLMClient"),
    # ファクトリ
    "create_unified_llm_client": ("src.core.llm.factory", "create_unified_llm_client"),
    # src/llm/ からの re-export（後方互換ブリッジ）
    "LLMCircuitBreaker": ("src.llm.circuit_breaker", "LLMCircuitBreaker"),
    "ResilientLLMGateway": ("src.llm.resilient_gateway", "ResilientLLMGateway"),
    "LLMProvider": ("src.llm.base", "LLMProvider"),
    "LLMResponsePydantic": ("src.llm.base", "LLMResponse"),
    "resolve_model": ("src.llm.model_router", "resolve_model"),
    "resolve_model_for_purpose": ("src.llm.model_router", "resolve_model_for_purpose"),
    "select_model": ("src.llm.model_router", "select_model"),
    "is_openai_compatible": ("src.llm.model_router", "is_openai_compatible"),
    # 低レベルクライアント
    "BaseLLMClient": ("src.core.llm_clients.base", "BaseLLMClient"),
    "GeminiApiClient": ("src.core.llm_clients.gemini", "GeminiApiClient"),
    "OpenAIApiClient": ("src.core.llm_clients.openai", "OpenAIApiClient"),
}

if TYPE_CHECKING:  # pragma: no cover - 型チェック/static analysis のみ
    from src.core.llm.types import LLMRequest, LLMResponse, LLMUsage, StreamChunk  # noqa: F401
    from src.core.llm.unified_interface import IUnifiedLLMClient  # noqa: F401
    from src.core.llm.adapters.gemini_unified_client import GeminiUnifiedClient  # noqa: F401
    from src.core.llm.adapters.mock_unified_client import UnifiedMockLLMClient  # noqa: F401
    from src.core.llm.adapters.openai_unified_client import OpenAIUnifiedClient  # noqa: F401
    from src.core.llm.factory import create_unified_llm_client  # noqa: F401
    from src.core.llm_clients.base import BaseLLMClient  # noqa: F401
    from src.core.llm_clients.gemini import GeminiApiClient  # noqa: F401
    from src.core.llm_clients.openai import OpenAIApiClient  # noqa: F401
    from src.llm.base import LLMProvider  # noqa: F401
    from src.llm.base import LLMResponse as LLMResponsePydantic  # noqa: F401
    from src.llm.circuit_breaker import LLMCircuitBreaker  # noqa: F401
    from src.llm.model_router import (  # noqa: F401
        is_openai_compatible,
        resolve_model,
        resolve_model_for_purpose,
        select_model,
    )
    from src.llm.resilient_gateway import ResilientLLMGateway  # noqa: F401


def __getattr__(name: str) -> Any:
    """公開シンボルを初回アクセス時に import する (PEP 562)。"""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module_path, attr = target
    value = getattr(importlib.import_module(module_path), attr)
    globals()[name] = value  # 2 回目以降は __getattr__ を経由しない
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    # 統合インターフェース
    "IUnifiedLLMClient",
    "LLMRequest",
    "LLMResponse",
    "LLMUsage",
    "StreamChunk",
    # アダプタ
    "GeminiUnifiedClient",
    "OpenAIUnifiedClient",
    "UnifiedMockLLMClient",
    # ファクトリ
    "create_unified_llm_client",
    # ゲートウェイ・サーキットブレーカー（src/llm/ からの re-export）
    "LLMCircuitBreaker",
    "ResilientLLMGateway",
    "LLMProvider",
    "LLMResponsePydantic",
    # モデルルーター
    "resolve_model",
    "resolve_model_for_purpose",
    "select_model",
    "is_openai_compatible",
    # 低レベルクライアント
    "BaseLLMClient",
    "GeminiApiClient",
    "OpenAIApiClient",
]
