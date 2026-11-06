from typing import Any

from src.backend.config import settings
from src.llm.unified.interface import IUnifiedLLMClient
from src.llm.unified.adapters.claude import ClaudeUnifiedClient
from src.llm.unified.adapters.gemini import GeminiUnifiedClient
from src.llm.unified.adapters.mock import UnifiedMockLLMClient
from src.llm.unified.adapters.ollama import OllamaUnifiedClient
from src.llm.unified.adapters.openai import OpenAIUnifiedClient


def create_unified_llm_client(provider_name: str, **kwargs: Any) -> IUnifiedLLMClient:
    """指定プロバイダ名の LLM クライアントを生成する。

    プロバイダ固有の引数（api_key 等）は kwargs から明示的に取り出し、
    未指定時は `src.backend.config.settings` の既定値を使用する。
    """
    provider = provider_name.strip().lower()

    if provider == "mock":
        return UnifiedMockLLMClient(**kwargs)

    if provider == "openai":
        return OpenAIUnifiedClient(
            api_key=kwargs.pop("api_key", settings.OPENAI_API_KEY),
            base_url=kwargs.pop("base_url", settings.OPENAI_BASE_URL or "https://api.openai.com/v1"),
            **kwargs,
        )

    if provider == "claude":
        return ClaudeUnifiedClient(
            api_key=kwargs.pop("api_key", settings.ANTHROPIC_API_KEY),
            model_name=kwargs.pop("model_name", settings.ANTHROPIC_MODEL),
            **kwargs,
        )

    if provider == "gemini":
        return GeminiUnifiedClient(
            api_key=kwargs.pop("api_key", settings.GEMINI_API_KEY),
            model=kwargs.pop("model", settings.GEMINI_MODEL),
            **kwargs,
        )

    if provider in ("ollama", "vllm"):
        return OllamaUnifiedClient(
            api_key=kwargs.pop("api_key", None),
            base_url=kwargs.pop("base_url", None),
            model=kwargs.pop("model", None),
            **kwargs,
        )

    raise ValueError(f"Unknown provider: {provider_name}")
