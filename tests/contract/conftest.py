"""Contract テスト用共有フィクスチャと設定."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def contract_client():
    """Contract テスト用の TestClient フィクスチャ.

    OpenAPI スキーマを取得するために使用します。

    NOTE: ``app`` の import はモジュール直下に置かない。このファイルは
    初期 conftest として ``tests/conftest.py`` の ``pytest_configure``
    （``AUTH_DISABLED=true`` の設定）**より先**に import され得る。
    そこで ``Settings`` が ``AUTH_DISABLED=False`` で生成・固定されると、
    同一セッションの後続テスト（``tests/test_styles_router.py`` 等）が
    401 になる。フィクスチャ内 import は収集後なので安全。
    """
    from src.backend.server import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def openapi_schema(contract_client):
    """OpenAPI スキーマを取得するフィクスチャ."""
    response = contract_client.get("/openapi.json")
    assert response.status_code == 200, "OpenAPI スキーマを取得できませんでした"
    return response.json()
