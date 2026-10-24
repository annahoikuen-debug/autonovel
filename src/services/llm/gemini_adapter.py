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

#: generate_text の max_tokens 引数既定値。
DEFAULT_MAX_TOKENS = 2000
#: JSON 生成で max_tokens が既定のままのときに引き当てる出力上限。
#: 切り残しを防ぐための既定であり、呼び出し側の明示指定は常に優先される。
JSON_DEFAULT_MAX_OUTPUT_TOKENS = 16384


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
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """テキストを一括生成する。"""
        client = self._get_client()
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        # JSON生成時はスキーマ全体の出力が数千〜1万トークンに達するため、
        # 思考トークンで上限が圧迫されて途中で切れるのを防ぐために thinking_budget=0 を設定
        types = _genai_types()
        is_json = bool(response_format and response_format.get("type") in ("json_object", "json_schema"))
        # 呼び出し側が明示的に max_tokens を指定した場合はそれを尊重する。
        # 旧実装は JSON 時に無条件で max(max_tokens, 16384) とし、
        # 小さな JSON を大量生成する経路でコストとレイテンシが暴走していた。
        # 既定値 (DEFAULT_MAX_TOKENS) のまま (= 呼び出し側が指定していない) 場合
        # のみ、JSON の切り残しを防ぐため引き上げる。
        if is_json and max_tokens == DEFAULT_MAX_TOKENS:
            resolved_max_tokens = JSON_DEFAULT_MAX_OUTPUT_TOKENS
        else:
            resolved_max_tokens = max_tokens

        config_kwargs: dict[str, Any] = {
            "max_output_tokens": resolved_max_tokens,
            "temperature": temperature,
        }
        if hasattr(types, "ThinkingConfig"):
            try:
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except Exception:
                pass
        if is_json:
            config_kwargs["response_mime_type"] = "application/json"

        models_to_try = [self.model_name]
        for fallback_model in ("gemini-3.5-flash-lite", "gemini-2.5-flash-lite"):
            if fallback_model not in models_to_try:
                models_to_try.append(fallback_model)

        async def _call() -> str:
            last_err = None
            for model_cand in models_to_try:
                curr_config = dict(config_kwargs)
                if "3.5-flash-lite" in model_cand:
                    curr_config.pop("thinking_config", None)
                try:
                    response = await client.aio.models.generate_content(
                        model=model_cand,
                        contents=full_prompt,
                        config=types.GenerateContentConfig(**curr_config),
                    )
                    return response.text or ""
                except Exception as e:
                    last_err = e
                    err_str = str(e)
                    if "thinking_config" in curr_config and "400" in err_str:
                        try:
                            curr_config.pop("thinking_config", None)
                            response = await client.aio.models.generate_content(
                                model=model_cand,
                                contents=full_prompt,
                                config=types.GenerateContentConfig(**curr_config),
                            )
                            return response.text or ""
                        except Exception as e2:
                            last_err = e2
                            err_str = str(e2)
                    if "429" in err_str or "quota" in err_str.lower() or "503" in err_str:
                        logger.warning("Model %s returned quota/unavailable (%s). Trying next fallback model...", model_cand, e)
                        continue
                    raise
            if last_err:
                raise last_err
            return ""

        return await with_retry(_call)

    async def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
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
