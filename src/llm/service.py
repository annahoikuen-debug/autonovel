from __future__ import annotations

"""LLM 統合サービス。

src.llm.adapters.factory.get_llm_adapter への委譲を提供する。
3レイヤーモデルルータによる用途別最適化も兼ねる。

PLAN_Q3: 旧 shim（DeprecationWarning 付き）から正規モジュールに昇格。
"""

import json
import logging
from typing import Any

from src.llm.model_router import resolve_model_for_purpose

logger = logging.getLogger(__name__)


class LLMService:
    """用途別モデル解決とクライアントファクトリへの委譲を提供する LLM 統合サービス。"""

    def __init__(self, llm: Any = None, repo: Any = None, **kwargs: Any):
        self.llm = llm
        self.repo = repo
        self._kwargs = kwargs

    def _ensure_factory(self):

        return self

    def get_client(self, model_name: str | None = None):
        """モデル名から LLM アダプタを取得する。"""
        from src.llm.adapters.factory import get_llm_adapter

        return get_llm_adapter(model_name=model_name)

    def _resolve_model(self, purpose_or_request: Any, model_name: str | None) -> str | None:
        """明示的 model_name が無ければ purpose からモデルを解決する。"""
        if model_name is not None:
            return model_name
        purpose = str(purpose_or_request or "writing")
        return resolve_model_for_purpose(purpose, {})

    async def generate(self, prompt: str, system_prompt: str | None = None, **kwargs: Any) -> str:
        """プロンプトからテキストを生成する。"""
        from src.llm.adapters.factory import get_llm_adapter

        adapter = get_llm_adapter(model_name=kwargs.get("model_name"))
        return await adapter.generate_text(
            prompt=prompt, system_prompt=system_prompt or "", max_tokens=kwargs.get("max_tokens", 2000)
        )

    async def generate_text(
        self,
        purpose_or_request: Any = "writing",
        prompt: str = "",
        system_prompt: str | None = None,
        temp: float = 0.7,
        model_name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """テキスト生成（旧 LLMGateway.generate_text 互換）。

        アダプタの生レスポンスをそのまま返す（GenerateResult に包まない）。

        Args:
            purpose_or_request: 用途名（モデル解決に使用）。モデル未指定時は必須。
            prompt: 生成プロンプト。
            system_prompt: システム指示。
            temp: 生成温度（0-1）。
            model_name: 明示モデル名。指定時は purpose による解決をスキップ。
        """
        resolved_model = self._resolve_model(purpose_or_request, model_name)
        adapter = self.get_client(model_name=resolved_model)
        return await adapter.generate_text(
            prompt=prompt,
            system_prompt=system_prompt or "",
            max_tokens=kwargs.get("max_tokens", 2000),
            temperature=temp,
            stream_callback=kwargs.get("stream_callback"),
        )

    async def generate_json(
        self,
        purpose_or_request: Any = "writing",
        prompt: str = "",
        response_schema: Any = None,
        system_instruction: str | None = None,
        temp: float = 0.7,
        model_name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """JSON 生成（旧 LLMGateway.generate_json 互換）。

        アダプタに ``generate_json`` が無い場合は ``generate_text`` をフォールバックとし、
        応答テキストを JSON パースして返す（GenerateResult に包まない）。

        Args:
            purpose_or_request: 用途名（モデル解決に使用）。
            prompt: 生成プロンプト。
            response_schema: 応答スキーマ（現状はアダプタ側で無視、後方互換のため保持）。
            system_instruction: システム指示。
            temp: 生成温度（0-1）。
            model_name: 明示モデル名。
        """
        resolved_model = self._resolve_model(purpose_or_request, model_name)
        adapter = self.get_client(model_name=resolved_model)

        if hasattr(adapter, "generate_json"):
            return await adapter.generate_json(
                model_name=resolved_model,
                prompt=prompt,
                response_schema=response_schema,
                system_prompt=system_instruction or "",
                temp=temp,
                stream_callback=kwargs.get("stream_callback"),
            )

        # Fallback: generate_text で JSON テキストを生成しパースする。
        response_format = {"type": "json_object"}
        if response_schema is not None:
            response_format = {"type": "json_object", "schema": response_schema}
        text = await adapter.generate_text(
            prompt=prompt,
            system_prompt=system_instruction or "",
            max_tokens=kwargs.get("max_tokens", 2000),
            temperature=temp,
            response_format=response_format,
            stream_callback=kwargs.get("stream_callback"),
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLMService.generate_json: response was not valid JSON, returning raw text")
            return text

    def resolve_model(self, purpose: str, llm_config: dict | None = None, **kwargs: Any) -> str:
        """用途別モデルを解決する (後方互換メソッド)。"""
        return resolve_model_for_purpose(purpose, llm_config or {})


__all__: list[str] = ["LLMService"]
