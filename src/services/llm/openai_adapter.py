"""OpenAI および OpenAI 互換 API (Ollama, LocalAI, vLLM, DeepSeek等) のアダプタ。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from src.backend.config import settings
from src.services.llm.base import (
    PLACEHOLDER_API_KEY,
    BaseLLMAdapter,
    is_placeholder_api_key,
)
from src.services.llm.retry import with_retry

logger = logging.getLogger(__name__)


class OpenAIAdapter(BaseLLMAdapter):
    """OpenAI 互換 API アダプタ。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.OPENAI_API_KEY or PLACEHOLDER_API_KEY
        self.base_url = base_url or settings.OPENAI_BASE_URL
        self.model = model or settings.OPENAI_MODEL
        if is_placeholder_api_key(self.api_key):
            # ローカル OpenAI 互換エンドポイント (Ollama 等) はキー不要なので
            # ここでは例外にせず、警告のみで設定不足を可視化する。
            logger.warning(
                "OpenAIAdapter initialised without a real API key "
                "(OPENAI_API_KEY unset). "
                "Requests to a remote api.openai.com endpoint will fail with HTTP 401."
            )
        self._client: Any = None

    @property
    def client(self) -> Any:
        """OpenAI クライアントを遅延生成して返す。

        openai SDK の import は数秒を要すため、実際に API を呼ぶまで
        生成しない (起動時間短縮)。
        """
        if self._client is None:
            from openai import AsyncOpenAI  # 遅延 import

            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    @client.setter
    def client(self, value: Any) -> None:
        # テストや呼び出し側からの差し替えを従来どおり許可する。
        self._client = value

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """テキストを一括生成する (リトライ付き、Structured Outputs対応)。"""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        call_kwargs = dict(kwargs)
        if response_format is not None:
            call_kwargs["response_format"] = response_format

        async def _call() -> str:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=temperature,
                **call_kwargs,
            )
            choice = response.choices[0]
            return choice.message.content or ""

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
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            **kwargs,
        )

        # response is AsyncStream[ChatCompletionChunk] when stream=True
        async for chunk in response:  # type: ignore[union-attr]
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
