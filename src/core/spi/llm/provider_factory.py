"""LLM Provider Factory.

本ファクトリは **テスト/開発用のモックのみ** を返す。

実運用の LLM 呼び出しは `src/services/llm`（`get_llm_adapter`）または
`src/core/llm_gateway.py` の `LLMProviderFactory` を使うこと。ここに
「プロバイダ名を受け取りながら本物を返さない」実装を残しておくことで、
本番出力が捏造される経路を作らないことを優先する。
"""

from __future__ import annotations

from typing import Any

from src.core.spi.llm.interface import ILLMProvider
from src.core.spi.llm.mock_adapter import MockLLMProvider

#: このファクトリが構築できるプロバイダ。モック以外は意図的に空。
_SUPPORTED_PROVIDERS = frozenset({"mock"})


class LLMProviderFactory:
    """Factory for creating test/mock LLM provider instances."""

    def __init__(self, **kwargs: Any) -> None:
        self.default_kwargs = kwargs

    def create(self, provider_type: str = "mock", **kwargs: Any) -> ILLMProvider:
        """Create a mock LLM provider instance.

        Raises:
            ValueError: ``mock`` 以外のプロバイダが指定された場合。
                黙ってモックへフォールバックすると、呼び出し側は
                「実APIが返した文章」と誤認して本番品質を損なうため、
                要求されたプロバイダが未対応であることを明示的に通知する。
        """
        normalized = (provider_type or "mock").lower()
        if normalized not in _SUPPORTED_PROVIDERS:
            raise ValueError(
                f"LLMProviderFactory はモックのみ提供のため、provider_type={provider_type!r} "
                f"はサポートされていません。実運用では "
                "`src.services.llm.get_llm_adapter` を使用してください。"
            )
        merged_kwargs = {**self.default_kwargs, **kwargs}
        return MockLLMProvider(**merged_kwargs)
