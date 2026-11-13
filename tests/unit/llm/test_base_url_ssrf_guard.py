"""Step 3 (H1): llm_config.base_url の SSRF＋APIキー流出遮断。

H1: base_url にプライベート IP / メタデータ IP (169.254.x.x 等) を指定すると
サーバー側リクエスト偽造（SSRF）となり、api_key 未指定時にサーバーの
OPENAI_API_KEY が攻撃者ホストに Bearer 送出される。
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from src.llm.adapters.factory import (
    _validate_base_url,
    get_llm_adapter,
)


def test_link_local_metadata_ip_blocked():
    """169.254.169.254 (AWS メタデータ) は常にブロック（H1）。"""
    with pytest.raises(ValueError, match="リンクローカル"):
        _validate_base_url("http://169.254.169.254/latest/meta-data/", allow_private=False)


def test_private_ip_blocked_in_production(monkeypatch):
    """プライベート IP (10.x, 172.16.x, 192.168.x) は production でブロック（H1）。"""
    from src.backend import config as cfg_module

    monkeypatch.setattr(cfg_module.settings, "APP_ENV", "production")
    try:
        with pytest.raises(ValueError, match="プライベートアドレス"):
            _validate_base_url("http://10.0.0.1:8000/v1", allow_private=False)
        with pytest.raises(ValueError, match="プライベートアドレス"):
            _validate_base_url("http://172.16.0.1:8000/v1", allow_private=False)
        with pytest.raises(ValueError, match="プライベートアドレス"):
            _validate_base_url("http://192.168.1.1:8000/v1", allow_private=False)
    finally:
        monkeypatch.undo()


def test_private_ip_allowed_in_development():
    """development ではプライベート IP は許可（ローカル Ollama/vLLM 用）。"""
    os.environ["APP_ENV"] = "development"
    try:
        # 例外が出ないこと
        _validate_base_url("http://localhost:11434/v1", allow_private=False)
        _validate_base_url("http://192.168.1.100:11434/v1", allow_private=False)
    finally:
        os.environ["APP_ENV"] = "testing"


def test_public_url_allowed():
    """通常の公開エンドポイントは通る（正常系回帰）。"""
    _validate_base_url("https://api.openai.com/v1", allow_private=False)
    _validate_base_url("https://openrouter.ai/api/v1", allow_private=False)


def test_base_url_without_api_key_rejected(monkeypatch):
    """base_url 指定時に api_key 未指定ならサーバーキー流出を防ぐ（H1）。"""
    # testing 環境では get_llm_adapter が mock を返すため、development に変更
    os.environ["APP_ENV"] = "development"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-server-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    try:
        with pytest.raises(ValueError, match="api_key も必須"):
            get_llm_adapter(
                provider="openai",
                base_url="https://attacker.example.com/v1",
                # api_key を渡さない
            )
    finally:
        os.environ["APP_ENV"] = "testing"


def test_public_base_url_with_api_key_allowed(monkeypatch):
    """base_url + api_key 両方指定なら正常にアダプタが生成される（正常系回帰）。"""
    os.environ["APP_ENV"] = "development"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    try:
        adapter = get_llm_adapter(
            provider="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-user-key",
        )
        assert adapter is not None
    finally:
        os.environ["APP_ENV"] = "testing"


def test_private_base_url_blocked_in_production_integration(monkeypatch):
    """get_llm_adapter で production 時のプライベート IP base_url は拒否される（H1）。"""
    from src.backend import config as cfg_module

    monkeypatch.setattr(cfg_module.settings, "APP_ENV", "production")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-server-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    try:
        with pytest.raises(ValueError, match="リンクローカル"):
            get_llm_adapter(
                provider="openai",
                base_url="http://169.254.169.254/latest/meta-data/",
                api_key="sk-user-key",
            )
    finally:
        monkeypatch.undo()
