"""Play モード動的継続生成の WS E2E テスト (ADR 002 / PLAN_P1 TRACK-P / P6)。

`tests/branches/test_e2e_ws.py` の fixture パターンを踏襲する。
flag OFF（既定）では error 応答のみ・flag ON では生成 → 新ノード → セッション移動が完走する。
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.backend.database.models import Base, Book, User
from src.backend.observability import metrics as _metrics


def _scene_metric_total() -> float:
    """play_dynamic_scenes_total のカウンタ合計(未初期化なら 0)。

    `_created` サンプル(Unix タイムスタンプ)は除外する。
    """
    return sum(
        s.value
        for family in _metrics.play_dynamic_scenes_total.collect()
        for s in family.samples
        if s.name.endswith("_total")
    )


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

    original_db_url = core_mod.DATABASE_URL
    original_core_get_db_manager = core_mod.get_db_manager

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
            user = User(
                id=1,
                email="dyn-ws@example.com",
                hashed_password="not-used-in-this-test",
                display_name="Dynamic WS",
                role="admin",
                status="active",
            )
            s.add(user)
            b = Book(title="t", genre="g", concept="c", current_branch_id=1, user_id=user.id)
            s.add(b)
            await s.commit()

    asyncio.run(_setup())

    owner = User(id=1, email="dyn-ws@example.com", role="admin", status="active")

    from src.backend.auth import get_current_user, validate_api_key_or_raise
    from src.backend.routers import branches as bmod

    original_bmod_get_db_manager = bmod.get_db_manager
    original_verify_book_ownership = bmod.verify_book_ownership
    original_make_llm = bmod._make_dynamic_llm

    bmod.get_db_manager = core_mod.get_db_manager

    async def _fake_verify_book_ownership(book_id, current_user, uow=None):
        return Book(id=book_id, user_id=1)

    bmod.verify_book_ownership = _fake_verify_book_ownership
    # 動的生成の LLM をモック（決定論的 JSON 応答）
    async def _fake_llm(prompt: str) -> str:
        return json.dumps({"scene": "夜風の中、彼は剣を抜いた。", "choices": ["前へ進む", "休む"]}, ensure_ascii=False)

    bmod._make_dynamic_llm = lambda: _fake_llm

    app = FastAPI()
    app.dependency_overrides[validate_api_key_or_raise] = lambda: "testkey"
    app.dependency_overrides[get_current_user] = lambda: owner
    app.include_router(bmod.router)

    yield TestClient(app)

    core_mod.DATABASE_URL = original_db_url
    core_mod.get_db_manager = original_core_get_db_manager
    bmod.get_db_manager = original_bmod_get_db_manager
    bmod.verify_book_ownership = original_verify_book_ownership
    bmod._make_dynamic_llm = original_make_llm
    app.dependency_overrides.clear()
    import asyncio as _asyncio

    _asyncio.run(test_engine.dispose())
    try:
        db_path.unlink(missing_ok=True)
    except OSError:
        pass


def _ws_headers() -> dict:
    from src.backend.security.jwt import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user_id='1', role='admin')}"}


def _setup_play(client):
    """分岐 + グラフ + セッションを作成し session_id を返す。"""
    r = client.post("/api/branches/", json={"book_id": 1, "name": "dyn"})
    assert r.status_code == 201
    bid = r.json()["id"]
    graph = {
        "entry_node_id": "n1",
        "nodes": {
            "n1": {"id": "n1", "episode_num": 1, "content": "start", "branch_type": "choice", "choices": []}
        },
    }
    client.put(f"/api/branches/1/graph?branch_id={bid}", json=graph)
    return client.post("/api/branches/play", json={"book_id": 1, "branch_id": bid}).json()["session_id"]


def test_dynamic_continue_disabled_by_default(client):
    """flag OFF（既定）: dynamic_continue は error 応答のみ（off 差分ゼロ契約）。"""
    sid = _setup_play(client)
    with client.websocket_connect(f"/api/branches/play/{sid}/ws", headers=_ws_headers()) as ws:
        initial = ws.receive_json()
        assert initial["type"] == "state"
        assert initial["dynamic_available"] is False

        ws.send_json({"action": "dynamic_continue", "choice_text": "前へ進む"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert resp["message"] == "dynamic continuation is disabled"


def test_dynamic_continue_full_flow(client):
    """flag ON: 選択 → 生成 → 新ノード追加 → セッション移動が完走する。

    メトリクスの陽性対照も兼ねる: 成功 1 回で play_dynamic_scenes_total が
    ちょうど 1 増えること（無音性契約の逆側。契約テストの恒真排除と対になる）。
    """
    from src.backend.routers import branches as bmod

    sid = _setup_play(client)
    with client.websocket_connect(f"/api/branches/play/{sid}/ws", headers=_ws_headers()) as ws:
        initial = ws.receive_json()
        assert initial["type"] == "state"
        metric_before = _scene_metric_total()

        bmod.settings.ENABLE_DYNAMIC_BRANCH = True
        try:
            ws.send_json({"action": "dynamic_continue", "choice_text": "前へ進む"})
            scene = ws.receive_json()
            assert scene["type"] == "dynamic_scene"
            assert "剣" in scene["text"]
            assert scene["choices"][0]["text"] == "前へ進む"
            assert scene["dynamic_count"] == 1

            state = ws.receive_json()
            assert state["type"] == "state"
            # セッションが新ノードへ移動している
            assert state["current_node_id"] == scene["node_id"]
            assert state["dynamic_available"] is True
            assert state["dynamic_count"] == 1
            # 陽性対照: 成功 1 回でカウンタが +1
            assert _scene_metric_total() == pytest.approx(metric_before + 1)
        finally:
            bmod.settings.ENABLE_DYNAMIC_BRANCH = False


def test_dynamic_continue_respects_session_limit(client):
    """コスト上限（P5）: 上限超過時は error 応答になる。"""
    from src.backend.routers import branches as bmod

    sid = _setup_play(client)
    with client.websocket_connect(f"/api/branches/play/{sid}/ws", headers=_ws_headers()) as ws:
        initial = ws.receive_json()
        assert initial["type"] == "state"

        bmod.settings.ENABLE_DYNAMIC_BRANCH = True
        original_limit = bmod.settings.PLAY_DYNAMIC_MAX_PER_SESSION
        bmod.settings.PLAY_DYNAMIC_MAX_PER_SESSION = 0  # 上限 0 = 即時拒否
        try:
            ws.send_json({"action": "dynamic_continue", "choice_text": "x"})
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert resp["message"] == "dynamic limit reached"
        finally:
            bmod.settings.ENABLE_DYNAMIC_BRANCH = False
            bmod.settings.PLAY_DYNAMIC_MAX_PER_SESSION = original_limit


def test_dynamic_continue_rest_disabled_by_default(client):
    """flag OFF（既定）: REST dynamic は 503（off 差分ゼロ契約の HTTP レベル検証）。

    review-loop Round 1 指摘 1（ブロッカー）: これまで WS 経路のみの検証で、
    REST の flag ゲートが実 HTTP レベルで未テストだった。
    """
    sid = _setup_play(client)
    r = client.post(
        f"/api/branches/play/{sid}/dynamic",
        json={"choice_text": "前へ進む"},
        headers=_ws_headers(),
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "dynamic continuation is disabled"


def test_dynamic_continue_rest_full_flow(client):
    """flag ON: REST でも選択 → 生成 → 新ノード → セッション移動が完走する。"""
    from src.backend.routers import branches as bmod

    sid = _setup_play(client)
    bmod.settings.ENABLE_DYNAMIC_BRANCH = True
    try:
        r = client.post(
            f"/api/branches/play/{sid}/dynamic",
            json={"choice_text": "前へ進む"},
            headers=_ws_headers(),
        )
        assert r.status_code == 200
        body = r.json()
        assert "剣" in body["scene"]["text"]
        assert body["scene"]["dynamic_count"] == 1
        assert body["state"]["current_node_id"] == body["scene"]["node_id"]
    finally:
        bmod.settings.ENABLE_DYNAMIC_BRANCH = False


def test_existing_choose_unaffected(client):
    """既存 choose は動的継続追加の影響を受けない（既存挙動不変）。"""
    r = client.post("/api/branches/", json={"book_id": 1, "name": "c"})
    bid = r.json()["id"]
    graph = {
        "entry_node_id": "n1",
        "nodes": {
            "n1": {
                "id": "n1",
                "episode_num": 1,
                "content": "start",
                "branch_type": "choice",
                "choices": [{"id": "c1", "text": "go", "target_node_id": "n2"}],
            },
            "n2": {"id": "n2", "episode_num": 2, "content": "end", "branch_type": "merge", "merge_target": "n2"},
        },
    }
    client.put(f"/api/branches/1/graph?branch_id={bid}", json=graph)
    sid = client.post("/api/branches/play", json={"book_id": 1, "branch_id": bid}).json()["session_id"]

    with client.websocket_connect(f"/api/branches/play/{sid}/ws", headers=_ws_headers()) as ws:
        initial = ws.receive_json()
        assert initial["type"] == "state"
        assert initial["available_choices"] == [{"id": "c1", "text": "go", "target_node_id": "n2"}]

        ws.send_json({"action": "choose", "choice_id": "c1"})
        state = ws.receive_json()
        assert state["type"] == "state"
        assert state["current_node_id"] == "n2"
