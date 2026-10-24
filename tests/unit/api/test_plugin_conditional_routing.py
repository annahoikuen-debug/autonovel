"""Step 19 検証テスト: マルチメディア無効時の FastAPI ルーター軽量化.

ENABLE_MULTIMEDIA フラグに応じて /multimedia ルーターが条件付きマウントされる
ことを検証する。
"""

from __future__ import annotations

import importlib
import sys

from fastapi import FastAPI

from src.core.plugin_registry import PluginRegistry


def _fresh_server_module(monkeypatch, enable_multimedia: bool | None):
    """server.py をフラグ付きで再インポートし、(app, registry) を返す。"""
    if enable_multimedia is None:
        monkeypatch.delenv("ENABLE_MULTIMEDIA", raising=False)
    else:
        monkeypatch.setenv("ENABLE_MULTIMEDIA", str(enable_multimedia).lower())
    # モジュールキャッシュから除外して再評価
    sys.modules.pop("src.backend.server", None)
    sys.modules.pop("src.core.plugin_registry", None)
    server = importlib.import_module("src.backend.server")
    registry = importlib.import_module("src.core.plugin_registry")
    return server, registry


def _mounted_paths(app: FastAPI) -> set[str]:
    """マウント済みルートのパス一覧を返す。

    FastAPI 0.141 以降 ``include_router`` は ``_IncludedRouter`` という遅延
    ラッパーを ``app.routes`` に積むため、``route.path`` を直接列挙すると
    マウント済みのルーターまで「無い」ことになってしまう（偽陰性）。
    OpenAPI スキーマを生成させると遅延分も解決済みのパスが返るため、
    そちらを正とする。
    """
    return set(app.openapi().get("paths", {}))


def _has_multimedia_route(app: FastAPI) -> bool:
    """/multimedia プレフィックスのルートがマウントされているか。"""
    return any(path.startswith("/multimedia") for path in _mounted_paths(app))


class TestConditionalRouting:
    def test_multimedia_router_skipped_when_disabled(self, monkeypatch):
        """ENABLE_MULTIMEDIA 未設定時、/multimedia ルートがマウントされないこと。"""
        server, _ = _fresh_server_module(monkeypatch, enable_multimedia=None)
        assert not _has_multimedia_route(server.app)

    def test_multimedia_router_mounted_when_enabled(self, monkeypatch):
        """ENABLE_MULTIMEDIA=true 時、/multimedia ルートがマウントされること。"""
        server, _ = _fresh_server_module(monkeypatch, enable_multimedia=True)
        assert _has_multimedia_route(server.app)

    def test_core_routes_mounted_regardless(self, monkeypatch):
        """コアルーター (/health) はフラグに関係なくマウントされること。"""
        server, _ = _fresh_server_module(monkeypatch, enable_multimedia=None)
        assert "/health" in _mounted_paths(server.app)

    def test_explicit_false_disables(self, monkeypatch):
        server, _ = _fresh_server_module(monkeypatch, enable_multimedia=False)
        assert not _has_multimedia_route(server.app)


class TestRegistryGating:
    def test_registry_flag_matches_routing(self, monkeypatch):
        """PluginRegistry の判定とルーティング挙動が一致すること。"""
        for enabled in (True, False):
            monkeypatch.setenv("ENABLE_MULTIMEDIA", str(enabled).lower())
            registry = PluginRegistry()
            assert registry.is_enabled("multimedia") is enabled
