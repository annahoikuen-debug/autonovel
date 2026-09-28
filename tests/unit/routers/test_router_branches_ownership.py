"""branches ルータの所有者検証（IDOR 対策）の検証。

``requires_book_ownership`` は handler をラップせず FastAPI 依存として
注入する実装になっている。ここでは

- HTTP 経由では所有者検証が実際に走る（book_id / current_user が渡る）
- 非所有者は 403、認証無い場合は 401
- book_id を持たない /play/* 系は影響を受けない
- handler を直接呼び出した場合（単体テスト経路）は検証が走らない

ことを確認する。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

import src.backend.routers.branches as branches_module
from src.backend.routers.branches import router as branches_router
from src.backend.routers.branches import get_branch_diff

OWNER_ID = 999
CURRENT = [SimpleNamespace(id=OWNER_ID, role="user")]


async def _fake_current_user() -> SimpleNamespace:
    return CURRENT[0]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(branches_router)
    app.dependency_overrides[branches_module.get_current_user] = _fake_current_user
    return app


def test_non_owner_is_rejected_with_403():
    seen: list[tuple[int, int | None]] = []

    async def _verify(book_id, current_user, uow=None):
        seen.append((book_id, getattr(current_user, "id", None)))
        if current_user.id != OWNER_ID:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Access denied")

    with patch.object(branches_module, "verify_book_ownership", _verify):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        CURRENT[0] = SimpleNamespace(id=OWNER_ID, role="user")
        ok = client.get("/api/branches/10/diff", params={"branchA": 1, "branchB": 2, "chapter": 3})
        assert ok.status_code != 403, f"所有者は通るはず: {ok.status_code}"
        assert seen, "所有者検証が呼ばれていない"

        CURRENT[0] = SimpleNamespace(id=123, role="user")
        denied = client.get("/api/branches/10/diff", params={"branchA": 1, "branchB": 2, "chapter": 3})
        assert denied.status_code == 403, f"非所有者は 403 のはず: {denied.status_code}"


def test_anonymous_is_rejected_with_401():
    """current_user を解決できない場合は 401。"""

    async def _anonymous():
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Not authenticated")

    app = _make_app()
    app.dependency_overrides[branches_module.get_current_user] = _anonymous
    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/api/branches/10/diff", params={"branchA": 1, "branchB": 2, "chapter": 3})
    assert res.status_code == 401, f"未認証は 401 のはず: {res.status_code}"


def test_play_routes_are_unaffected():
    """book_id を持たない /play/* 系は所有者検証の対象にしない（登録が壊れない）。"""
    paths = {r.path for r in branches_router.routes}
    play = [p for p in paths if "/play" in p]
    assert play, "/play 系が存在しない"
    for route in branches_router.routes:
        if "/play" in route.path:
            assert "current_user" not in {
                p.name for p in inspect_params(route)
            }, f"所有者検証が注入された /play ルート: {route.path}"

def test_direct_call_skips_ownership_check():
    """handler を直接呼び出した場合、検証は走らない（単体テストが動く理由）。"""

    async def _boom(*a, **k):
        raise AssertionError("直接呼び出しでは所有者検証が走らないはず")

    with patch.object(branches_module, "verify_book_ownership", _boom):
        # session を渡さないので途中で止まるが、所有权検証の AssertionError ではない
        import asyncio

        with pytest.raises(Exception) as exc:
            asyncio.get_event_loop().run_until_complete(
                get_branch_diff(10, branchA=1, branchB=2, chapter=3, session=AsyncMock())
            )
        assert "所有者検証が走らないはず" not in str(exc.value)


def inspect_params(route):
    import inspect

    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return ()
    return list(dependant.query_params)
