"""Multimedia ルータの統合テスト (self-contained FastAPI app)。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.backend import config
from src.backend.auth import get_current_user, validate_api_key_or_raise
from src.backend.database.models import User
from src.backend.multimedia_service import MultimediaResult
from src.backend.routers import multimedia as multimedia_router


@pytest.fixture
def mm_auth_user() -> User:
    """`get_current_user` オーバーライド用の認証済みユーザー。

    `validate_api_key_or_raise` のオーバーライドだけでは `get_current_user` は
    差し替わらないため、認証をバイパスするには本フィクスチャも必要。
    """
    return User(id=1, email="test@example.com", role="admin", status="active")


@pytest.fixture
def mm_client(monkeypatch, tmp_path, mm_auth_user):
    """`/multimedia` 系の TestClient。Multimedia を有効化し、`MultimediaService` をスタブ。"""
    monkeypatch.setattr(config.settings, "ENABLE_MULTIMEDIA", True)
    monkeypatch.setattr(config.settings, "MULTIMEDIA_OUTPUT_DIR", str(tmp_path / "mm"))

    # サービススタブ
    stub = MagicMock()
    stub.generate_media_mix.return_value = MultimediaResult(
        asset_id=1, files=["/tmp/manga.json"], metadata={"format": "manga"}
    )
    stub.export_ebook.return_value = MultimediaResult(
        asset_id=2, files=["/tmp/book.epub"], metadata={"formats": ["epub"]}
    )
    stub.generate_if_routes.return_value = (
        MultimediaResult(asset_id=3, files=["/tmp/graph.json"], metadata={"node_count": 2}),
        MagicMock(entry_node_id="ep1", nodes={"ep1": MagicMock(to_dict=lambda: {"id": "ep1"})}),
    )
    stub.generate_asset_pack.return_value = (
        MultimediaResult(asset_id=4, files=["/tmp/pack.zip"], metadata={"item_count": 1}),
        "task-123",
    )
    stub.get_artifact.return_value = {
        "asset_id": 1,
        "book_id": 1,
        "asset_type": "media_mix",
        "format": "manga",
        "file_path": "/tmp/manga.json",
        "metadata": {},
        "created_at": "2026-09-02T00:00:00",
    }
    stub.get_task.return_value = {
        "task_id": "task-123",
        "asset_id": 4,
        "status": "completed",
        "error": None,
        "started_at": "2026-09-02T00:00:00",
        "finished_at": "2026-09-02T00:00:01",
    }

    app = FastAPI()
    app.include_router(multimedia_router.router, prefix="/multimedia", tags=["multimedia"])
    app.dependency_overrides[multimedia_router.get_multimedia_service] = lambda: stub
    app.dependency_overrides[validate_api_key_or_raise] = lambda: "test-key"
    app.dependency_overrides[get_current_user] = lambda: mm_auth_user
    # 所有権ガードは AppContainer.db() を使うため、スタブサービスだけでは検証できない。
    # エンドポイント自体はそのまま（所有権チェックの通過のみスタブする）。
    ownership_stub = AsyncMock(return_value=MagicMock(id=1, user_id=mm_auth_user.id))
    monkeypatch.setattr(multimedia_router, "verify_book_ownership", ownership_stub)

    from src.backend.rate_limit import generate_limiter
    generate_limiter.reset()

    with TestClient(app) as client:
        yield client, stub


def test_media_mix_endpoint(mm_client):
    client, _ = mm_client
    res = client.post("/multimedia/media-mix", json={"book_id": 1, "format": "manga"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["asset_id"] == 1
    assert body["files"] == ["/tmp/manga.json"]


def test_ebook_endpoint(mm_client):
    client, _ = mm_client
    res = client.post("/multimedia/ebook", json={"book_id": 1, "formats": ["epub"]})
    assert res.status_code == 200
    body = res.json()
    assert body["asset_id"] == 2
    assert "epub" in body["formats"]


def test_if_routes_endpoint(mm_client):
    client, _ = mm_client
    res = client.post("/multimedia/if-routes", json={"book_id": 1})
    assert res.status_code == 200
    body = res.json()
    assert body["entry_node_id"] == "ep1"


def test_asset_pack_endpoint(mm_client):
    client, _ = mm_client
    res = client.post(
        "/multimedia/asset-pack",
        json={"book_id": 1, "include_if_routes": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["task_id"] == "task-123"


def test_task_status_endpoint(mm_client):
    client, _ = mm_client
    res = client.get("/multimedia/tasks/task-123")
    assert res.status_code == 200
    assert res.json()["status"] == "completed"


def test_artifact_metadata_endpoint(mm_client):
    client, _ = mm_client
    res = client.get("/multimedia/artifacts/1")
    assert res.status_code == 200
    body = res.json()
    assert body["asset_id"] == 1
    assert body["book_id"] == 1


def test_disabled_returns_503(monkeypatch, tmp_path, mm_auth_user):
    monkeypatch.setattr(config.settings, "ENABLE_MULTIMEDIA", False)
    app = FastAPI()
    app.include_router(multimedia_router.router, prefix="/multimedia", tags=["multimedia"])
    app.dependency_overrides[validate_api_key_or_raise] = lambda: "k"
    app.dependency_overrides[get_current_user] = lambda: mm_auth_user
    with TestClient(app) as c:
        res = c.post("/multimedia/media-mix", json={"book_id": 1})
    assert res.status_code == 503
    assert "Multimedia" in res.text


def test_path_traversal_blocked(monkeypatch, tmp_path, mm_auth_user):
    monkeypatch.setattr(config.settings, "ENABLE_MULTIMEDIA", True)
    monkeypatch.setattr(config.settings, "MULTIMEDIA_OUTPUT_DIR", str(tmp_path / "mm"))
    app = FastAPI()
    app.include_router(multimedia_router.router, prefix="/multimedia", tags=["multimedia"])
    app.dependency_overrides[validate_api_key_or_raise] = lambda: "k"
    app.dependency_overrides[get_current_user] = lambda: mm_auth_user
    monkeypatch.setattr(
        multimedia_router, "verify_book_ownership", AsyncMock(return_value=MagicMock(id=1))
    )
    with TestClient(app) as c:
        # Starlette/FastAPI の URL バリデーションで `..` は 400 を返す
        res = c.get("/multimedia/files/..%2F..%2Fetc%2Fpasswd", follow_redirects=False)
    assert res.status_code in (400, 404)
