"""LLM アダプタの抽象基底クラス。"""

from __future__ import annotations

import asyncio
import concurrent.futures
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any
import warnings


#: API キーが未設定のときに使うプレースホルダ。
#: ローカル LLM (Ollama / LocalAI / vLLM) は正当なキーが不要なので、
#: 設定の欠如ではなく「未設定である」ことを明示的に観測可能にするための値。
#: 実キーが設定されている場合はこのプレースホルダに一切影響しない。
PLACEHOLDER_API_KEY = "__AUTONOVEL_API_KEY_NOT_SET__"

#: 過去のハードコードされたダミー値 (後方互換の判定用)。
_LEGACY_PLACEHOLDERS = frozenset(
    {"DUMMY", "dummy", "dummy_key_for_local", "dummy_key_for_testing", "dummy-key"}
)


class LLMConfigurationError(RuntimeError):
    """LLM の設定不足/不整合を示す明確なエラー。"""


def is_placeholder_api_key(api_key: str | None) -> bool:
    """API キーがプレースホルダ (未設定) かどうか."""
    if not api_key:
        return True
    return api_key == PLACEHOLDER_API_KEY or api_key in _LEGACY_PLACEHOLDERS


def ensure_api_key_configured(
    api_key: str | None,
    provider: str,
    env_var: str,
) -> str:
    """API キーがプレースホルダのままだ면明確な設定エラーを送出する.

    ローカル互換エンドポイント (キー不要) では呼び出さないこと。
    """
    if is_placeholder_api_key(api_key):
        raise LLMConfigurationError(
            f"{provider} API key is not configured: set the {env_var} environment "
            f"variable (or settings.{env_var}) before calling the remote API. "
            "A placeholder key was detected, which would otherwise surface as an "
            "opaque HTTP 401/403."
        )
    return str(api_key)


class BaseLLMAdapter(ABC):
    """LLM プロバイダの共通インターフェース。"""

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """テキストを一括生成する。"""
        warnings.warn(
            "BaseLLMAdapter is deprecated, use IUnifiedLLMClient instead",
            DeprecationWarning,
            stacklevel=2,
        )
        raise NotImplementedError

    @abstractmethod
    async def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """テキストをストリーミング生成する。"""
        warnings.warn(
            "BaseLLMAdapter is deprecated, use IUnifiedLLMClient instead",
            DeprecationWarning,
            stacklevel=2,
        )
        raise NotImplementedError
        yield ""  # generator 型ヒント用

    def cancel(self) -> None:
        """進行中のストリームをキャンセルするフック。既定は何もしない。"""
        return None

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """同期コンテキスト向けの生成メソッド（イベントループを安全に処理）。"""
        warnings.warn(
            "BaseLLMAdapter is deprecated, use IUnifiedLLMClient instead",
            DeprecationWarning,
            stacklevel=2,
        )
        coro = self.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
            **kwargs,
        )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
