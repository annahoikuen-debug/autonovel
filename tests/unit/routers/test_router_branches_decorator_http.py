"""`requires_book_ownership` デコレータ経由の HTTP 経路の回帰テスト。

このテストが固定する問題
----------------------
``requires_book_ownership`` は handler をラップせず、
``__signature__`` に ``current_user: User = Depends(enforce_book_ownership)`` を
追加する実装だった。

FastAPI は解決した依存を**全て kwargs で渡す**ため、
``current_user`` を宣言していない handler では
``TypeError: unexpected keyword argument 'current_user'`` が発生し、
``@requires_book_ownership`` を付けた**全ルートが 500** になっていた
（``PUT /api/branches/{book_id}/graph`` を含む）。

修正は「依存の注入」のまま保ちつつ、薄いラッパーを被せて
``current_user`` だけを吸収させる形（``branches.py`` の ``wrapper``）。
本テストは装飾されたルートが実際に 200/4xx を返し、500 にならないことを固定する。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.backend.routers.branches as branches_module
from src.backend.routers.branches import router as branches_router

OWNER_ID = 999
BOOK_ID = 10
BRANCH_ID = 1

# `@requires_book_ownership` が付いている book_id ルーティング
# (登録パス, HTTP メソッド, 実リクエストパス, リクエストボディ)。
# 装飾漏れを早期に気づけるように列挙する。
# ボディは「handler まで到達する」ための最小限の有効値にしてある
# （422 で止まると TypeError の 500 を検出できないため）。
DECORATED_ROUTES = (
    (
        "/api/branches/{book_id}/merge/preview",
        "post",
        "/api/branches/10/merge/preview",
        {"source_branch_id": 1, "target_branch_id": 2, "merge_ep_num": 3},
    ),
    ("/api/branches/{book_id}/graph", "put", "/api/branches/10/graph", {"entry_node_id": "n1", "nodes": {}}),
    ("/api/branches/{book_id}/nodes/{node_id}", "delete", "/api/branches/10/nodes/n1", None),
    ("/api/branches/{book_id}/editor/validate", "post", "/api/branches/10/editor/validate", {}),
)


async def _fake_current_user() -> SimpleNamespace:
    return SimpleNamespace(id=OWNER_ID, role="user", status="active")


async def _fake_session():
    """`get_branch_session` の代用。commit が呼べればよい。"""
    yield AsyncMock()


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(branches_router)
    app.dependency_overrides[branches_module.get_current_user] = _fake_current_user
    return app


def _patch_all(fake_repo: MagicMock):
    """所有者検証・セッション・リポジトリを差し替える。"""
    return (
        patch.object(branches_module, "verify_book_ownership", AsyncMock(return_value=None)),
        patch.object(branches_module, "get_branch_session", _fake_session),
        patch.object(branches_module, "BranchRepository", MagicMock(return_value=fake_repo)),
    )


def test_every_decorated_route_is_registered():
    """列挙した装飾済みルートがすべて router に登録されている。"""
    paths = {r.path for r in branches_router.routes}
    for template_path, _method, _request_path, _body in DECORATED_ROUTES:
        assert template_path in paths, f"ルートが見つからない: {template_path}"


@pytest.mark.parametrize(
    "template_path,method,request_path,body",
    DECORATED_ROUTES,
)
def test_decorated_route_does_not_return_500(
    template_path: str, method: str, request_path: str, body: dict | None
):
    """``@requires_book_ownership`` 付きルートが TypeError 起因の 500 を返さない。

    旧実装（ラッパー無し）では、この経路は必ず 500 になっていた。
    """
    fake_repo = MagicMock(
        get_branch=AsyncMock(return_value=None),
        load_branch_graph=AsyncMock(return_value=None),
    )
    owner_patch, session_patch, repo_patch = _patch_all(fake_repo)
    with owner_patch, session_patch, repo_patch:
        client = TestClient(_make_app(), raise_server_exceptions=False)
        if method == "delete":
            res = client.delete(request_path)
        else:
            res = getattr(client, method)(
                request_path, json=body, params={"branch_id": BRANCH_ID}
            )

    assert res.status_code != 500, (
        f"{method.upper()} {template_path} が 500"
        f"（`current_user` の想定外 kwargs）: {res.text}"
    )


def test_save_branch_graph_returns_valid_response():
    """``PUT /api/branches/{book_id}/graph`` が 200 と正しいボディを返す。"""
    branch = SimpleNamespace(id=BRANCH_ID, book_id=BOOK_ID)
    fake_repo = MagicMock(
        get_branch=AsyncMock(return_value=branch),
        save_branch_graph=AsyncMock(return_value=None),
    )
    payload = {"entry_node_id": "n1", "nodes": {"n1": {"id": "n1", "choices": []}}}

    owner_patch, session_patch, repo_patch = _patch_all(fake_repo)
    with owner_patch, session_patch, repo_patch:
        client = TestClient(_make_app(), raise_server_exceptions=False)
        res = client.put(
            f"/api/branches/{BOOK_ID}/graph",
            params={"branch_id": BRANCH_ID},
            json=payload,
        )

    assert res.status_code == 200, f"500 ではなく 200 のはず: {res.status_code} {res.text}"
    assert res.json() == {"branch_id": BRANCH_ID, "graph": payload}
    fake_repo.save_branch_graph.assert_awaited_once_with(BRANCH_ID, payload)


def test_save_branch_graph_rejects_other_book_branch():
    """別作品のブランチを保存先に指定したら 404（book_id の越境防止）。"""
    branch = SimpleNamespace(id=BRANCH_ID, book_id=BOOK_ID + 1)  # 別作品のもの
    fake_repo = MagicMock(get_branch=AsyncMock(return_value=branch))

    owner_patch, session_patch, repo_patch = _patch_all(fake_repo)
    with owner_patch, session_patch, repo_patch:
        client = TestClient(_make_app(), raise_server_exceptions=False)
        res = client.put(
            f"/api/branches/{BOOK_ID}/graph",
            params={"branch_id": BRANCH_ID},
            json={"entry_node_id": "n1", "nodes": {}},
        )

    assert res.status_code == 404, f"別作品のブランチは 404 のはず: {res.status_code}"


def test_ownership_helper_receives_a_user_object():
    """``verify_book_ownership`` が `User` 以外の型を受け取らないことを固定する。

    依存注入の差し替えが崩れると、ここに `Depends` オブジェクトや
    ``None`` が渡るため `book.user_id != current_user_id` が常に真になり、
    理由不明の 403 になる。ここでは「User 相当のオブジェクトが届く」ことを見る。
    """
    seen: list[tuple[int, object]] = []

    async def _capture(book_id, current_user, uow=None):
        seen.append((book_id, current_user))

    with patch.object(branches_module, "verify_book_ownership", _capture), patch.object(
        branches_module, "get_branch_session", _fake_session
    ), patch.object(
        branches_module,
        "BranchRepository",
        MagicMock(
            return_value=MagicMock(
                get_branch=AsyncMock(return_value=SimpleNamespace(id=BRANCH_ID, book_id=BOOK_ID)),
                save_branch_graph=AsyncMock(return_value=None),
            )
        ),
    ):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        res = client.put(
            f"/api/branches/{BOOK_ID}/graph",
            params={"branch_id": BRANCH_ID},
            json={"entry_node_id": "n1", "nodes": {}},
        )

    assert res.status_code == 200, f"200 のはず: {res.status_code} {res.text}"
    assert seen, "所有者検証が呼ばれていない"
    book_id, current_user = seen[0]
    assert book_id == BOOK_ID
    assert isinstance(current_user, SimpleNamespace), (
        f"verify_book_ownership に User 以外が届いた: {type(current_user)!r}"
    )
    assert current_user.id == OWNER_ID
