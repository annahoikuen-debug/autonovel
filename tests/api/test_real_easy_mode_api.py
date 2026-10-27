"""
本物の FastAPI Easy Mode API 整合性検証テスト (Step 7)
"""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def test_client(client, db_session):
    """FastAPI TestClient フィクスチャ。

    独自の ``TestClient(app)`` を作ると環境変数 ``DATABASE_URL``（リポジトリの
    autonovel.db）を直接参照し、``tasks`` テーブルが無い/Alembic 未適用で
    ``sqlite3.OperationalError: no such table: tasks`` になる。
    conftest の ``client`` フィクスチャは ``db_session``（= ``real_db_manager``）を
    ``database.get_db`` に override して ``Base.metadata.create_all`` 済みの
    一時 SQLite を使うため、周辺状態に依存しない。

    加えて、AUTH_DISABLED 時に ``get_current_user_or_api_key_owner`` が返す
    開発用モックユーザー (id=1) を実 DB に登録する。``tasks.user_id`` は
    ``users.id`` への外部キーのため、``users`` に 1 行も無いと
    ``sqlite3.IntegrityError: FOREIGN KEY constraint failed`` で 500 になる。
    """
    from src.backend.auth import _get_dev_mock_user
    from src.backend.database.models import User

    dev_user = _get_dev_mock_user()
    db_session.add(
        User(
            id=dev_user.id,
            email=dev_user.email,
            # AUTH_DISABLED 下では照合されないが NOT NULL なのでダミーを入れる
            hashed_password="dev-mock-not-verified",
            display_name=dev_user.display_name,
            role=dev_user.role,
            status=dev_user.status,
            plan_tier=dev_user.plan_tier,
            credits=dev_user.credits,
        )
    )
    db_session.commit()

    yield client


def test_easy_mode_invalid_input_returns_422(test_client):
    """制限範囲外（content_length_limit=0 など）送信時に 422 Unprocessable Entity が返ること"""
    response = test_client.post(
        "/easy_mode/generate",
        json={"content_length_limit": 0}  # ge=1 なのでバリデーション違反
    )
    assert response.status_code == 422


@patch("src.backend.tasks.generation_tasks.generate_chapter_orchestrated_task")
def test_easy_mode_generate_enqueues_task(mock_task, test_client):
    """有効なリクエスト送信時に非同期生成タスクがキューに投入され、タスクIDが返ること"""
    unique_task_id = f"test-task-{uuid.uuid4()}"
    mock_result = MagicMock()
    mock_result.id = unique_task_id
    mock_task.return_value = mock_result

    payload = {
        "character_params": {
            "name": "アレン",
            "personality": "冷静沈着",
            "ability": "空間魔法"
        },
        "current_chapter": "第1話：目覚め",
        "genre": "異世界ファンタジー",
        "content_length_limit": 2000,
        "target_episodes": 1
    }

    response = test_client.post("/easy_mode/generate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["task_id"] == unique_task_id
    assert "suggestions" in data


@patch("src.backend.tasks.generation_tasks.generate_chapter_orchestrated_task")
def test_easy_mode_generate_records_task_owner(mock_task, test_client):
    """投入したタスクに所有者が記録される（`/status/{task_id}` から読めなくなるのを防ぐ）。

    旧実装は `create_task(task_id=..., status="running")` と `user_id` を渡さないため
    `Task.user_id` が NULL になり、同一ファイル内の `get_task_status` が
    `_assert_task_ownership` で **自分の** タスクを拒否していた。

    `BookRepository` を差し替えて `create_task*` の引数そのものを検証する
    （実際にどの DB に書かれるかはテストの実行順で変わるため、
    行を読み返す方式では他のテストと干渉して不安定になる）。
    """
    from src.backend.routers import easy_mode as easy_mode_module

    unique_task_id = f"test-task-{uuid.uuid4()}"
    mock_result = MagicMock()
    mock_result.id = unique_task_id
    mock_task.return_value = mock_result

    payload = {
        "character_params": {"name": "アレン", "personality": "冷静沈着", "ability": "空間魔法"},
        "current_chapter": "第1話：目覚め",
        "genre": "異世界ファンタジー",
        "content_length_limit": 2000,
        "target_episodes": 1,
    }

    fake_repo = MagicMock()
    fake_repo.is_async = False
    fake_repo.create_task = MagicMock()
    fake_repo.create_task_async = AsyncMock()

    with patch.object(easy_mode_module, "BookRepository", MagicMock(return_value=fake_repo)):
        response = test_client.post("/easy_mode/generate", json=payload)

    assert response.status_code == 200, f"200 のはず: {response.status_code} {response.text}"
    assert fake_repo.create_task.called or fake_repo.create_task_async.await_count, (
        "タスクレコードが作成されていない"
    )

    recorder = fake_repo.create_task if fake_repo.create_task.called else None
    call_kwargs = (
        fake_repo.create_task.call_args.kwargs
        if recorder is not None
        else fake_repo.create_task_async.await_args.kwargs
    )
    assert call_kwargs.get("user_id") is not None, (
        f"Task.user_id が NULL になる: {call_kwargs}"
    )


def test_easy_mode_generate_rejects_unattributable_caller(test_client, monkeypatch):
    """所有者を特定できない呼び出し（API キー単独）は投入時点で 403。

    旧実装は所有者のないタスクを無言で作り、後から `/status` で読めなくなるだけだった。
    """
    import src.backend.auth as auth_module
    from src.backend.routers import easy_mode as easy_mode_module

    monkeypatch.setattr(easy_mode_module.settings, "AUTH_DISABLED", False)
    monkeypatch.setattr(
        auth_module.settings, "ALLOWED_API_KEYS", "test-easy-mode-key", raising=False
    )

    payload = {
        "character_params": {"name": "アレン", "personality": "冷静沈着", "ability": "空間魔法"},
        "current_chapter": "第1話：目覚め",
        "genre": "異世界ファンタジー",
        "content_length_limit": 2000,
        "target_episodes": 1,
    }

    with patch("src.backend.tasks.generation_tasks.generate_chapter_orchestrated_task") as mock_task:
        mock_result = MagicMock()
        mock_result.id = "should-not-be-enqueued"
        mock_task.return_value = mock_result

        response = test_client.post(
            "/easy_mode/generate",
            json=payload,
            headers={"Authorization": "test-easy-mode-key"},
        )

    assert response.status_code == 403, (
        f"所有者を特定できないなら投入時点で 403 のはず: {response.status_code}"
    )
    mock_task.assert_not_called()
