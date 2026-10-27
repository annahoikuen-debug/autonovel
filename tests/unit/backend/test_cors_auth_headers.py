"""未認証 401 時の CORS ヘッダー検証テスト"""
from fastapi.testclient import TestClient
from src.backend.server import app

def test_unauthorized_response_contains_cors_headers(monkeypatch):
    """未認証リクエストが 401 になり、その 401 にも CORS ヘッダが付くことを検証する。

    tests/conftest.py は全テストで `AUTH_DISABLED=true` を設定するため、そのままだと
    認証がバイパスされて 200 が返り、本テストの意図した 401 経路を検証できない。
    検証対象の経路（認証失敗）を確実ASEDに通すため、認証を明示的に有効化する。
    """
    from src.backend.config import settings

    monkeypatch.setattr(settings, "AUTH_DISABLED", False)

    client = TestClient(app)
    response = client.get(
        "/api/books",
        headers={"Origin": "http://localhost:5173"}
    )
    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"
