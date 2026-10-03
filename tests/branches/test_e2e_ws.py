"""Episode 6 S71: WebSocket E2E テスト."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.database.models import Base, Book, User


@pytest.fixture
def client():
    import tempfile
    from pathlib import Path

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db_url = f"sqlite+aiosqlite:///{db_path}"

    test_engine = create_async_engine(db_url, connect_args={"check_same_thread": False})
    test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    import src.backend.database.core as core_mod
    core_mod.DATABASE_URL = db_url

    class TestMgr:
        def __init__(self):
            self.session_factory = test_session_factory
            self.engine = test_engine
        def get_session(self):
            return self.session_factory()
    core_mod.get_db_manager = lambda: TestMgr()

    async def _setup():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with test_session_factory() as s:
            # 所有者ユーザーは WebSocket ハンドシェイク時の認証にも必要
            user = User(
                id=1,
                email="branches-ws@example.com",
                hashed_password="not-used-in-this-test",
                display_name="Branches WS",
                role="admin",
                status="active",
            )
            s.add(user)
            # `Book.user_id` が NULL の作品はアクセスできないため設定する
            b = Book(title="t", genre="g", concept="c", current_branch_id=1, user_id=user.id)
            s.add(b)
            await s.commit()

    asyncio.run(_setup())

    owner = User(id=1, email="branches-ws@example.com", role="admin", status="active")

    from src.backend.auth import get_current_user, validate_api_key_or_raise
    from src.backend.routers import branches as bmod
    # `branches.py` は `get_db_manager` を名前で import している
    # (`from ... import get_db_manager`) ため、`core_mod` 側の属性を差し替えるだけでは
    # 既に束縛済みの名前は更新されない。ルータモジュール側を直接パッチする。
    bmod.get_db_manager = core_mod.get_db_manager
    # `enforce_book_ownership` デコレータ (branches.py:70) はセッション引数なしで
    # `verify_book_ownership` を呼ぶため自身で UnitOfWork を開き、一時 DB を見られない。
    # ここを Book を返すスタブに差し替えてセッション境界を越えないようにする。
    # (他のルータテストと同じ方針: ガードはスタブするがハンドラ本体は最後まで実行する)
    async def _fake_verify_book_ownership(book_id, current_user, uow=None):
        return Book(id=book_id, user_id=1)

    bmod.verify_book_ownership = _fake_verify_book_ownership

    app = FastAPI()
    app.dependency_overrides[validate_api_key_or_raise] = lambda: "testkey"
    # branches ルーターは `dependencies=[Depends(get_current_user)]` を持つ
    app.dependency_overrides[get_current_user] = lambda: owner
    app.include_router(bmod.router)
    return TestClient(app)


def test_ws_flow(client):
    from src.backend.security.jwt import create_access_token

    # WebSocket は dependency_overrides が効かないため、
    # `_authenticate_websocket` が `Authorization` ヘッダから読む JWT を渡す。
    token = create_access_token(data={"sub": "1", "role": "admin"})
    ws_headers = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/branches/", json={"book_id": 1, "name": "main"})
    assert r.status_code == 201, f"Status: {r.status_code}, Body: {r.text}"
    bid = r.json()["id"]
    graph = {
        "entry_node_id": "n1",
        "nodes": {
            "n1": {"id": "n1", "episode_num": 1, "content": "start", "branch_type": "choice",
                   "choices": [{"id": "c1", "text": "go", "target_node_id": "n2"}]},
            "n2": {"id": "n2", "episode_num": 2, "content": "end", "branch_type": "merge", "merge_target": "n2"},
        },
    }
    client.put(f"/api/branches/1/graph?branch_id={bid}", json=graph)

    sid = client.post("/api/branches/play", json={"book_id": 1, "branch_id": bid}).json()["session_id"]

    with client.websocket_connect(
        f"/api/branches/play/{sid}/ws", headers=ws_headers
    ) as ws:
        # initial state
        msg = ws.receive_json()
        assert msg["type"] == "state"
        assert msg["current_node_id"] == "n1"

        # choose
        ws.send_json({"action": "choose", "choice_id": "c1"})
        msg = ws.receive_json()
        assert msg["type"] == "state"
        assert msg["current_node_id"] == "n2"

        # save
        ws.send_json({"action": "save"})
        msg = ws.receive_json()
        assert msg["save_points_count"] == 1

        # load
        ws.send_json({"action": "load", "index": 0})
        msg = ws.receive_json()
        assert msg["current_node_id"] == "n2"

        # end
        ws.send_json({"action": "end"})
        msg = ws.receive_json()
        assert msg["type"] == "closed"
