"""LLM アダプタのファクトリモジュール。"""

from __future__ import annotations

import ipaddress
import logging
import os
import urllib.parse

from src.backend.config import settings
from src.llm.adapters.base import BaseLLMAdapter
from src.llm.adapters.claude import ClaudeAdapter
from src.llm.adapters.gemini import GeminiAdapter
from src.llm.adapters.mock import MockLLMAdapter
from src.llm.adapters.ollama import OllamaAdapter
from src.llm.adapters.openai import OpenAIAdapter
from src.llm.adapters.vllm import VLLMAdapter

logger = logging.getLogger(__name__)

IMPLEMENTED_PROVIDERS = {"gemini", "openai", "mock", "claude", "ollama", "vllm", "openrouter"}

# H1: SSRF 対策。リンクローカル（169.254.x.x / AWS メタデータ等）は常にブロック。
# プライベート IP は production のみブロック（development はローカル Ollama/vLLM 等を許容）。
_LINK_LOCAL_NETWORKS = [ipaddress.ip_network("169.254.0.0/16")]
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]


def _validate_base_url(base_url: str, allow_private: bool = False) -> None:
    """base_url が SSRF 対象（プライベートIP / メタデータIP）でないか検証する。

    ブロック時に ValueError を投げる。呼び出し側で 400 レスポンスに変換すること。
    """
    parsed = urllib.parse.urlparse(base_url)
    host = parsed.hostname or ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # ホスト名（DNS 名）はここで判定不可。DNS リバインディング対策は別途 WAF/プロキシ側で行う。
        return

    # リンクローカル（メタデータサービス等）は常にブロック
    if any(ip in net for net in _LINK_LOCAL_NETWORKS):
        raise ValueError(f"base_url のホスト {host} はリンクローカルアドレスのため利用不可")

    # プライベート IP は production のみブロック（development はローカル開発用を許容）
    if not allow_private and settings.APP_ENV == "production":
        if any(ip in net for net in _PRIVATE_NETWORKS):
            raise ValueError(f"base_url のホスト {host} はプライベートアドレスのため利用不可")


def get_llm_adapter(
    provider: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
) -> BaseLLMAdapter:
    """設定または引数に応じた LLM アダプタインスタンスを返す。

    未実装のプロバイダが指定された場合は WARNING ログを出力し、
    MockLLMAdapter にフォールバックする。
    """
    # In testing environment, always return mock to avoid API key requirements
    if os.environ.get("APP_ENV") == "testing":
        return MockLLMAdapter()

    p = (provider or settings.LLM_PROVIDER).lower()

    if p not in IMPLEMENTED_PROVIDERS:
        logger.warning(
            "LLMプロバイダ '%s' は未実装です。利用可能: %s。MockLLMAdapter にフォールバックします。",
            p,
            sorted(IMPLEMENTED_PROVIDERS),
        )
        return MockLLMAdapter()

    if p == "gemini":
        resolved_key = api_key or settings.GEMINI_API_KEY
        if not resolved_key:
            raise RuntimeError("GEMINI_API_KEY が未設定です。.env を確認してください。")
        return GeminiAdapter(api_key=resolved_key, model_name=model_name)

    if p == "openai":
        resolved_key = api_key or settings.OPENAI_API_KEY
        resolved_url = base_url or settings.OPENAI_BASE_URL
        if not resolved_key and not resolved_url:
            raise RuntimeError("OPENAI_API_KEY / OPENAI_BASE_URL が未設定です。.env を確認してください。")
        # H1: ユーザーが明示的に base_url を指定し、api_key を指定しない場合は
        # サーバーキー (OPENAI_API_KEY) の流出リスクがあるため拒否する。
        if base_url is not None and api_key is None:
            raise ValueError("base_url を指定する場合は api_key も必須です（サーバーキーの流出を防ぐため）")
        # H1: ユーザー指定の base_url がプライベート IP / メタデータ IP でないか検証
        if base_url is not None:
            _validate_base_url(resolved_url, allow_private=False)
        return OpenAIAdapter(api_key=resolved_key, base_url=resolved_url, model=model_name)

    if p == "openrouter":
        resolved_key = api_key or settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY
        if not resolved_key:
            raise RuntimeError("OPENROUTER_API_KEY (or OPENAI_API_KEY) が未設定です。.env を確認してください。")
        resolved_model = model_name or settings.OPENROUTER_MODEL
        # H1: base_url 指定時に api_key 未指定はサーバーキー流出リスク
        if base_url is not None and api_key is None:
            raise ValueError("base_url を指定する場合は api_key も必須です（サーバーキーの流出を防ぐため）")
        resolved_url = base_url or settings.OPENROUTER_BASE_URL
        if base_url is not None:
            _validate_base_url(resolved_url, allow_private=False)
        return OpenAIAdapter(
            api_key=resolved_key,
            base_url=resolved_url,
            model=resolved_model,
        )

    if p == "claude":
        resolved_key = api_key or settings.ANTHROPIC_API_KEY
        if not resolved_key:
            raise RuntimeError("ANTHROPIC_API_KEY が未設定です。.env を確認してください。")
        return ClaudeAdapter(api_key=resolved_key, model_name=model_name)

    if p == "ollama":
        resolved_url = base_url or settings.OLLAMA_BASE_URL
        if base_url is not None:
            _validate_base_url(resolved_url, allow_private=True)
        return OllamaAdapter(base_url=resolved_url, model=model_name)

    if p == "vllm":
        resolved_url = base_url or settings.VLLM_BASE_URL
        if base_url is not None:
            _validate_base_url(resolved_url, allow_private=True)
        return VLLMAdapter(base_url=resolved_url, model=model_name, api_key=api_key)

    if p == "mock":
        return MockLLMAdapter()

    return MockLLMAdapter()
