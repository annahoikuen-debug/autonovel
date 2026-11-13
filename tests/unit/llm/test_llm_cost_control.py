"""Step 17 (LLM コスト制御): Gemini max_output_tokens と LLMGateway トークン集計。

- gemini.py build_config_for_mode に max_output_tokens=2000 を追加（無制限課金防止）
- llm_gateway.py _usage_metric で prompt_token_count / candidates_token_count も試すように修正
  （クライアント側 MockUsage が prompt_token_count を返すため、従来は常に 0 集計だった）
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.llm_gateway import LLMGenerateResultProxy


class _FakeUsage:
    """クライアント側が返す usage オブジェクトを模擬（prompt_token_count / candidates_token_count）。"""

    def __init__(self, prompt: int = 100, candidates: int = 50):
        self.prompt_token_count = prompt
        self.candidates_token_count = candidates


def test_llm_gateway_usage_metric_reads_client_attributes():
    """_usage_metric が prompt_token_count / candidates_token_count を正しく読む（H17）。"""
    usage = _FakeUsage(prompt=123, candidates=456)
    assert LLMGenerateResultProxy._usage_metric(usage, "prompt_tokens", 0) == 123
    assert LLMGenerateResultProxy._usage_metric(usage, "completion_tokens", 0) == 456


def test_llm_gateway_usage_metric_none_returns_default():
    """usage が None ならデフォルト値を返す（H17）。"""
    assert LLMGenerateResultProxy._usage_metric(None, "prompt_tokens", 0) == 0


def test_llm_gateway_usage_metric_dict():
    """dict 形式の usage でも正しく取得できる（H17）。"""
    usage = {"prompt_tokens": 77, "completion_tokens": 88}
    assert LLMGenerateResultProxy._usage_metric(usage, "prompt_tokens", 0) == 77
    assert LLMGenerateResultProxy._usage_metric(usage, "completion_tokens", 0) == 88


def test_llm_gateway_usage_metric_unknown_key_returns_default():
    """存在しない属性ならデフォルト値を返す（H17）。"""
    usage = object()  # 任意の属性を持たないオブジェクト
    assert LLMGenerateResultProxy._usage_metric(usage, "nonexistent", 42) == 42


def test_gemini_build_config_has_max_output_tokens():
    """Gemini の GenerateContentConfig に max_output_tokens が含まれる（H17）。"""
    from src.llm.clients.gemini import GeminiApiClient
    from src.backend.engine_utils import AdaptiveCooldown

    client = GeminiApiClient(MagicMock(), AdaptiveCooldown(base_sec=2.0, min_sec=1.0, max_sec=60.0))
    config = client.build_config_for_mode(
        system_instruction="system",
        temp=0.7,
        attempt=0,
        response_schema=None,
        mode="native",
    )
    assert config.max_output_tokens == 2000
