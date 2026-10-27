"""Google Gemini API アダプタ (google.genai 新SDK完全準拠版)."""

from __future__ import annotations

import importlib
import logging
from collections.abc import AsyncIterator
from typing import Any, TYPE_CHECKING

from src.backend.config import settings
from src.services.llm.base import (
    PLACEHOLDER_API_KEY,
    BaseLLMAdapter,
    ensure_api_key_configured,
)
from src.services.llm.retry import with_retry

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _genai_types() -> Any:
    """``google.genai.types`` を遅延ロードして返す。

    google-genai SDK の import は数秒を要し、API サーバーの起動時には
    実際に Gemini を呼び出すまで不要。起動を遅くしないよう遅延させる。
    """
    return importlib.import_module("google.genai.types")


def __getattr__(name: str) -> Any:
    """``genai`` / ``types`` を遅延公開する (PEP 562)。"""
    if name == "genai":
        return importlib.import_module("google.genai")
    if name == "types":
        return _genai_types()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class GeminiAdapter(BaseLLMAdapter):
    """Google Gemini アダプタ (google.genai SDK)。"""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        resolved_key = api_key
        if not resolved_key:
            resolved_key = getattr(settings, "get_gemini_api_key", lambda: settings.GEMINI_API_KEY)() or ""
        self.api_key = resolved_key or PLACEHOLDER_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self._client: Any = None

    def _get_client(self) -> Any:
        """Client を遅延初期化する。"""
        if self._client is None:
            # Gemini API は常にリモートなので、キー未設定はそのまま渡すと
            # 不透明な 400/401 になる。明確な設定エラーに翻訳する。
            ensure_api_key_configured(
                self.api_key, provider="Gemini", env_var="GEMINI_API_KEY"
            )
            from google import genai  # 遅延 import（起動時間短縮のため）

            self._client = genai.Client(api_key=self.api_key)
        return self._client

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
        client = self._get_client()
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        config_kwargs: dict[str, Any] = {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format and response_format.get("type") in ("json_object", "json_schema"):
            config_kwargs["response_mime_type"] = "application/json"

        async def _call() -> str:
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config=_genai_types().GenerateContentConfig(**config_kwargs),
            )
            return response.text or ""

        return await with_retry(_call)

    async def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """テキストをストリーミング生成する。"""
        client = self._get_client()
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        response_stream = await client.aio.models.generate_content_stream(
            model=self.model_name,
            contents=full_prompt,
            config=_genai_types().GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        async for chunk in response_stream:
            if chunk.text:
                yield chunk.text
