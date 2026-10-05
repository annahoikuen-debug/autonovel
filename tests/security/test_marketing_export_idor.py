"""IDOR 修正の拒否契約テスト（`/api/marketing/export_package/{book_id}`）。

何が起きたか
------------
2026-10-04 の公開前監査で `POST /api/marketing/export_package/{book_id}` に
**水平権限昇格（IDOR）** が存在した。

```python
# 修正前
async def export_package_post(book_id: int, req: MarketingExportRequest):
    await validate_api_key_or_raise(req.api_key)     # 空文字で素通り
    zip_data, _ = await engine.marketing.create_export_package(book_id)
    # current_user 依存なし、verify_book_ownership なし
```

認証は `GlobalAuthMiddleware`（default-deny）が担保していたため、
**任意の認証済み一般ユーザーが任意の `book_id` を走査して
他人の作品 ZIP（本文・世界設定・プロット）を一括取得できた。**
同一ファイルの GET 版は正しく検証済みで、POST 版だけが未修正だった。

修正: `current_user` 依存と `verify_book_ownership` を追加。

本ファイルは**拒否が本当に機能すること**を固定する。
`tests/security/test_idor_regression.py` は静的ゲート（ガード呼び出しの有無）であり、
ここでは実際にリクエストを飛ばして応答コードを確認する。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def export_client(real_db_manager, monkeypatch):
    """認証・所有権の検証がimbibeされた経路を準備した TestClient。"""
    import os

    from dependency_injector import providers

    from src.backend.database.core import DatabaseManager
    from src.core.container import AppContainer

    AppContainer.db.override(
        providers.Object(DatabaseManager(os.environ["DATABASE_URL"]))
    )
    from src.backend.server import app

    yield TestClient(app)
    AppContainer.db.reset_override()


@pytest.fixture
def books(real_db_manager):
    """自分の作品 (id=1) と他人の作品 (id=2) を投入する。"""
    from src.backend.database.models import Book, User

    db = real_db_manager
    db.add_all(
        [
            User(id=1, email="me@example.com", hashed_password="x", display_name="me"),
            User(id=2, email="other@example.com", hashed_password="x", display_name="other"),
            Book(
                id=1,
                user_id=1,
                title="自分の作品",
                genre="F",
                concept="c",
                synopsis="s",
                target_eps=1,
            ),
            Book(
                id=2,
                user_id=2,
                title="他人の作品",
                genre="F",
                concept="c",
                synopsis="s",
                target_eps=1,
            ),
        ]
    )
    db.commit()
    return db


def _patch_engine(monkeypatch):
    """エクスポート本体をモック化し、所有权検証のみを観測する。"""
    from unittest.mock import AsyncMock, MagicMock

    from src.backend.routers import marketing as marketing_router

    fake_zip = b"PK\x03\x04"
    fake_engine = MagicMock()
    fake_engine.marketing.create_export_package = AsyncMock(
        return_value=(fake_zip, "export.zip")
    )
    monkeypatch.setattr(marketing_router, "get_engine", lambda *a, **k: fake_engine)
    return fake_engine


def _patch_user(monkeypatch, user_id: int) -> None:
    """`get_current_user` を一般ユーザー（admin ではない）に固定する。

    admin は `verify_book_ownership` の管理者は通過する（ただし作品の実在は
    要求される）ため、IDOR の検証には一般ユーザーを使う必要がある。
    """
    from src.backend.auth import get_current_user
    from src.backend.database.models import User
    from src.backend.server import app

    user = User(id=user_id, email=f"u{user_id}@example.com", hashed_password="x", display_name=f"u{user_id}")
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: user)


class TestExportPackageOwnershipEnforced:
    """POST 版に所有者検証が機能していることを固定する。"""

    def test_owner_can_export_own_book(self, export_client, books, monkeypatch) -> None:
        """自分の作品なら 200。"""
        _patch_user(monkeypatch, 1)
        _patch_engine(monkeypatch)
        resp = export_client.post(
            "/api/marketing/export_package/1", json={"api_key": "k"}
        )
        assert resp.status_code == 200, resp.text

    def test_non_owner_is_rejected(self, export_client, books, monkeypatch) -> None:
        """他人の作品は 403。IDOR の核心。"""
        _patch_user(monkeypatch, 1)
        engine = _patch_engine(monkeypatch)
        resp = export_client.post(
            "/api/marketing/export_package/2", json={"api_key": "k"}
        )
        assert resp.status_code == 403, (
            f"他人の作品にアクセスできてしまう: {resp.status_code} {resp.text}"
        )
        assert not engine.marketing.create_export_package.called, (
            "権限チェックを通過する前にエクスポート本体が呼ばれている"
        )

    def test_missing_book_is_404(self, export_client, books, monkeypatch) -> None:
        """存在しない book_id は 404。総当たり走査で何も抜けない。"""
        _patch_user(monkeypatch, 1)
        _patch_engine(monkeypatch)
        resp = export_client.post(
            "/api/marketing/export_package/99999", json={"api_key": "k"}
        )
        assert resp.status_code == 404, resp.text

    def test_get_and_post_enforce_ownership_consistently(
        self, export_client, books, monkeypatch
    ) -> None:
        """GET 版と POST 版が同じ判定を返すこと。

        修正前は GET のみ検証され POST は素通しだったため、
        2 つの版が同じ結果を返さないと実装の穴が残る。
        """
        _patch_user(monkeypatch, 1)
        _patch_engine(monkeypatch)
        post = export_client.post(
            "/api/marketing/export_package/2", json={"api_key": "k"}
        )
        get = export_client.get(
            "/api/marketing/export_package/2", headers={"X-API-Key": "k"}
        )
        assert post.status_code in (403, 404), post.status_code
        assert get.status_code in (403, 404), get.status_code
        assert post.status_code == get.status_code, (
            f"GET({get.status_code}) と POST({post.status_code}) の判定が異なる"
        )
