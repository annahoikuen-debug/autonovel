"""挿絵ルータの DI 解決 / Huey タスク化 / E2E テスト。

Step 28: AppContainer import バグ修正の検証。
Step 29-30: バッチ Huey 化 + status endpoint の検証。
Step 32: R15 safety の検証 (test_image_service.py に集約済み)。
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# GOOGLE_GENAI_API_KEY が未設定の CI 環境 대비
os.environ.setdefault("GOOGLE_GENAI_API_KEY", "test-key-for-di")


def test_dependencies_module_imports():
    """src.dependencies が import 可能で get_illustration_workflow を持つ。"""
    from src.dependencies import get_illustration_workflow

    assert callable(get_illustration_workflow)


def test_illustration_router_boots_without_name_error():
    """router import 時に AppContainer NameError が出ない (Step 28)。"""
    from src.backend.routers import illustrations as ill_router

    assert hasattr(ill_router, "router")
    # /generate と /batch の 2 ルート
    paths = {r.path for r in ill_router.router.routes}
    assert "/generate" in paths
    assert "/batch" in paths


def test_get_illustration_workflow_returns_workflow_instance():
    """get_illustration_workflow が IllustrationWorkflow インスタンスを返す。"""
    from src.dependencies import get_illustration_workflow

    with patch.dict(os.environ, {"GOOGLE_GENAI_API_KEY": "fake"}):
        wf = get_illustration_workflow()
    # 戻り値は IllustrationWorkflow (または MagicMock) であれば OK
    assert wf is not None
    # 必須メソッド
    assert hasattr(wf, "execute")
    assert hasattr(wf, "illustration_agent")


def test_illustration_router_batch_queues_task():
    """batch エンドポイント: 即座に task_id を返す (Huey キュー投入)。

    旧: バッチが同期で workflow.execute() の戻り値を返していた
    新: task_id を返してバックグラウンドで実行 → GET /status/{task_id} で取得
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    class _FakeWorkflow:
        """IllustrationWorkflow の代替 (duck-typing)。"""

        def __init__(self):
            self.illustration_agent = MagicMock()

        async def execute(self, **kwargs):
            return {
                "status": "success",
                "illustrations": [
                    {"id": 1, "url": "/img1.png"},
                    {"id": 2, "url": "/img2.png"},
                ],
            }

    # dependency_overrides で get_illustration_workflow の戻り値を差し替え
    from src.dependencies import get_illustration_workflow

    async def _override_workflow():
        return _FakeWorkflow()

    app = FastAPI()
    from src.backend.routers.illustrations import router

    app.include_router(router, prefix="/api/illustrations")
    app.dependency_overrides[get_illustration_workflow] = _override_workflow

    # 実装は book 所有権を検証する (IDOR 対策)。テスト環境に book はないためパッチ
    with (
        patch(
            "src.backend.routers.illustrations.verify_book_ownership",
            new=AsyncMock(return_value=None),
        ),
        TestClient(app) as client,
    ):
        resp = client.post(
            "/api/illustrations/batch",
            json={"book_id": 1, "settings": {"enableIllustration": True}},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert "task_id" in body


def test_illustration_router_generate_validation_error_returns_400():
    """generate エンドポイント: 不正リクエストで Pydantic 検証エラー (422)。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import src.backend.routers.illustrations as ill_module

    class _FakeWorkflow:
        def __init__(self):
            self.illustration_agent = MagicMock()

        async def execute(self, **kwargs):
            return {"status": "success"}

    async def _fake_dep():
        return _FakeWorkflow()

    ill_module.get_illustration_workflow = _fake_dep  # type: ignore[assignment]

    app = FastAPI()
    app.include_router(ill_module.router, prefix="/api/illustrations")

    with TestClient(app) as client:
        # book_id 欠落は Pydantic 検証エラー → FastAPI 標準の 422
        resp = client.post(
            "/api/illustrations/generate",
            json={"illustration_type": "cover"},
        )
    assert resp.status_code == 422


def test_illustration_batch_queues_huey_task():
    """batch エンドポイント: 即座に task_id を返し、Huey タスクが起動する。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # Huey を immediate モードに切替 (CI で redis/sqlite 不要)
    # 重要: src.backend.tasks パッケージは `huey` を属性に持つので、
    # モジュールは sys.modules から直接取得する。
    import sys

    huey_mod = sys.modules["src.backend.tasks.huey"]
    huey_instance = huey_mod.huey  # 実 Huey インスタンス

    original_immediate = huey_instance.immediate
    huey_instance.immediate = True
    try:
        app = FastAPI()
        from src.backend.routers.illustrations import router

        app.include_router(router, prefix="/api/illustrations")

        # 実装は book 所有権を検証する (IDOR 対策)。テスト環境に book はないためパッチ
        with (
            patch(
                "src.backend.routers.illustrations.verify_book_ownership",
                new=AsyncMock(return_value=None),
            ),
            TestClient(app) as client,
        ):
            resp = client.post(
                "/api/illustrations/batch",
                json={"book_id": 1, "settings": {"enableIllustration": True}},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "task_id" in body
        assert body["status"] in ("queued", "completed")
    finally:
        huey_instance.immediate = original_immediate


def test_illustration_status_endpoint_404():
    """存在しない task_id で 404。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    from src.backend.routers.illustrations import router

    app.include_router(router, prefix="/api/illustrations")

    with TestClient(app) as client:
        resp = client.get("/api/illustrations/status/nonexistent_task_id_xxx")
    assert resp.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_get_episode_illustration_prefers_episode_type(tmp_path):
    """GET /images/episode/{book_id}/{episode_number} の契約検証(Phase 3 Increment 1)。

    - episode_number 一致 + image_url 非空の行から illustration_type=episode を最優先する
    - image_url が空(プロンプトのみ)の行は found: false
    - episode_number < 1 は 422
    - IDOR 防止: verify_book_ownership が実行される(所有者なし作品は取得不可)
    """
    import asyncio

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.backend.auth import get_current_user
    from src.backend.database.core import DatabaseManager
    from src.backend.database.models import Base, Book, Illustration, User
    from src.backend.routers import illustrations as imod
    from src.core.container import AppContainer
    from src.core.exceptions.base import NotFoundError

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'ill.db'}"
    manager = DatabaseManager(db_url)

    async def _setup():
        async with manager.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with manager.get_session() as session:
            session.add(
                User(
                    id=1,
                    email="ill@example.com",
                    hashed_password="x",
                    display_name="t",
                    role="admin",
                    status="active",
                )
            )
            session.add(Book(id=1, title="t", genre="g", concept="c", current_branch_id=1, user_id=1))
            await session.commit()
            # FK(users→books)が解決した行を別コミットで積む(単一 flush での
            # 挿入順序と PRAGMA foreign_keys=ON の組合わせで FK 違反になるため分割)
            # 話数 2: episode 型を先に挿入し、より新しい id の cover 型より優先されることを検証
            session.add(
                Illustration(
                    book_id=1,
                    illustration_type="episode",
                    episode_number=2,
                    prompt="p2",
                    image_url="/static/illustrations/b.png",
                )
            )
            session.add(
                Illustration(
                    book_id=1,
                    illustration_type="cover",
                    episode_number=2,
                    prompt="p1",
                    image_url="/static/illustrations/a.png",
                )
            )
            # 話数 3: image_url 空(プロンプト生成のみ) → found: false
            session.add(
                Illustration(
                    book_id=1,
                    illustration_type="episode",
                    episode_number=3,
                    prompt="p3",
                    image_url="",
                )
            )
            await session.commit()

    asyncio.run(_setup())

    owner = User(id=1, email="ill@example.com", role="admin", status="active")
    app = FastAPI()
    app.include_router(imod.router)
    app.dependency_overrides[get_current_user] = lambda: owner

    try:
        with (
            patch.object(AppContainer, "db", return_value=manager),
            TestClient(app) as client,
        ):
            # 話数 2: episode 型を優先(id は cover の方が新しいが無視される)
            r = client.get("/images/episode/1/2")
            assert r.status_code == 200
            body = r.json()
            assert body["found"] is True
            assert body["image_url"] == "/static/illustrations/b.png"

            # 話数 3: 実画像なし → found: false(未生成と障害を区別する契約)
            r3 = client.get("/images/episode/1/3")
            assert r3.status_code == 200
            assert r3.json()["found"] is False

            # episode_number < 1 は 422
            r0 = client.get("/images/episode/1/0")
            assert r0.status_code == 422

            # 存在しない作品 → 所有権検証が NotFoundError を投げる(IDOR 防止)。
            # 本番アプリではグローバル例外ハンドラがこれを 404 に変換するが、
            # このテストの素の FastAPI() にはハンドラがないため例外が透過する
            with pytest.raises(NotFoundError):
                client.get("/images/episode/999/1")
    finally:
        asyncio.run(manager.engine.dispose())
