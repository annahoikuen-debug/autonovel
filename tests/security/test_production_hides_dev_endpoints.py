"""Step 19 (開発メトリ・ドキュメント露出の本番制限)。

- /metrics /docs /redoc /openapi.json を本番環境で非公開
- /api/system/models/info の configured_keys を admin のみに開示
"""
from __future__ import annotations

from src.backend.middleware.auth_middleware import is_public_path


def test_prod_hides_metrics_docs_openapi(monkeypatch):
    """本番環境では /metrics /docs /redoc /openapi.json が非公開（Step 19）。"""
    from src.backend import config as cfg_module

    monkeypatch.setattr(cfg_module.settings, "APP_ENV", "production")
    try:
        assert is_public_path("/metrics") is False
        assert is_public_path("/docs") is False
        assert is_public_path("/redoc") is False
        assert is_public_path("/openapi.json") is False
    finally:
        monkeypatch.undo()


def test_dev_shows_metrics_docs_openapi(monkeypatch):
    """開発環境では /metrics /docs /redoc /openapi.json が公開（正常系回帰）。"""
    from src.backend import config as cfg_module

    monkeypatch.setattr(cfg_module.settings, "APP_ENV", "development")
    try:
        assert is_public_path("/metrics") is True
        assert is_public_path("/docs") is True
        assert is_public_path("/redoc") is True
        assert is_public_path("/openapi.json") is True
    finally:
        monkeypatch.undo()


def test_health_stays_public_in_prod(monkeypatch):
    """本番環境でも /health/live は公開のまま（Step 19）。"""
    from src.backend import config as cfg_module

    monkeypatch.setattr(cfg_module.settings, "APP_ENV", "production")
    try:
        assert is_public_path("/health/live") is True
        assert is_public_path("/health/ready") is True
    finally:
        monkeypatch.undo()


def test_system_models_info_configured_keys_admin_only():
    """get_models_info の configured_keys は admin のみ真、それ以外は False（Step 19）。"""
    import inspect
    from src.backend.routers import system

    src = inspect.getsource(system.get_models_info)
    assert "is_admin" in src
    assert 'if is_admin else False' in src
