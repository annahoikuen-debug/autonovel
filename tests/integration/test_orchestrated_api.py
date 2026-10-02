# tests/integration/test_orchestrated_api.py
"""オーケストレーション API 統合テスト。

注: 既存ルーターの `illustration_agent.run(request=...)` 呼び出しが新シグネチャ
`(ctx: AgentContext)` と互換性がないため、`server.py` の動的ルーター登録が
ハングする場合がある。本テストはオーケストレーションルーターのみを
ロードして検証する。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestOrchestratedAPI:
    """オーケストレーション API テスト（ルーター単独ロード）。"""

    def _build_minimal_app(self):
        """オーケストレーションルーターのみを含む最小 FastAPI アプリ。"""
        app = FastAPI()
        from src.backend.routers.orchestrated import router as orchestrated_router

        # prefix は router 定義側（src/backend/routers/orchestrated.py）が持つ。
        # ここで重ねると /orchestrated/orchestrated/* になるため渡さない。
        app.include_router(orchestrated_router)
        return app

    @patch("src.backend.routers.orchestrated.BookRepository")
    @patch("src.backend.tasks.generation_tasks.generate_chapter_orchestrated_task")
    def test_generate_endpoint_returns_task_id(self, mock_task, mock_repo_cls):
        """POST /orchestrated/generate が task_id を返すこと。"""
        # テストごとにユニークな task_id を使う (共有DB の UNIQUE 制約回避)
        import uuid
        unique_id = f"test-task-{uuid.uuid4().hex[:8]}"
        mock_result = MagicMock()
        mock_result.id = unique_id
        mock_task.return_value = mock_result

        mock_repo = MagicMock()
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.user_id = 1
        mock_repo.get_book.return_value = mock_book
        mock_repo_cls.return_value = mock_repo

        app = self._build_minimal_app()
        client = TestClient(app)

        payload = {
            "book_id": 1,
            "branch_id": 1,
            "ep_num": 1,
            "title": "テスト作品",
            "synopsis": "テストあらすじ",
            "target_eps": 10,
            "genre": "fantasy",
        }
        response = client.post("/orchestrated/generate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert isinstance(data["message"], str)

    def test_generate_endpoint_validation(self):
        """必須フィールド未入力で 422 が返ること。"""
        app = self._build_minimal_app()
        client = TestClient(app)

        payload = {"book_id": 1}  # title 未入力
        response = client.post("/orchestrated/generate", json=payload)
        assert response.status_code == 422

    def test_status_endpoint_pending(self):
        """GET /orchestrated/status/{task_id} で存在しないタスクは pending。"""
        app = self._build_minimal_app()
        client = TestClient(app)

        response = client.get("/orchestrated/status/nonexistent_task_id")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["task_id"] == "nonexistent_task_id"

    @patch("src.backend.routers.orchestrated.huey")
    def test_cancel_endpoint(self, mock_huey):
        """DELETE /orchestrated/task/{task_id} が 200 を返すこと。"""
        app = self._build_minimal_app()
        client = TestClient(app)

        import uuid
        unique_id = f"test-task-{uuid.uuid4().hex[:8]}"
        response = client.delete(f"/orchestrated/task/{unique_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["task_id"] == unique_id


def test_orchestrated_routes_are_reachable():
    """orchestrated の 4 エンドポイントが app に載り、FE 契約パスで存在すること（404 防止）。

    frontend/src/api/orchestratedApi.ts の BASE は "/orchestrated" なので、
    server 側も /orchestrated/* で応答できる必要がある。
    """
    from src.backend.server import app

    paths = {r.path for r in app.routes}
    expected = {
        "/orchestrated/generate",
        "/orchestrated/status/{task_id}",
        "/orchestrated/task/{task_id}",
        "/orchestrated/export/{book_id}",
        "/orchestrated/events/{correlation_id}",
    }
    missing = sorted(expected - paths)
    assert not missing, f"orchestrated が未マウント、または prefix が FE 契約と不一致: {missing}"


def test_orchestrated_does_not_leak_unguarded_root_routes():
    """orchestrated の全ルートが router 定義の prefix 配下にあること。

    prefix を付けないと /generate や /status/{task_id} がルート直下に露出し、
    illustrations ルーターの同名ルートと衝突して FE からは /orchestrated/* が 404 になる。
    """
    from src.backend.routers.orchestrated import router as orchestrated_router

    leaked = sorted(
        r.path for r in orchestrated_router.routes if not r.path.startswith("/orchestrated")
    )
    assert not leaked, f"orchestrated が prefix 配下に無いルートがある: {leaked}"
