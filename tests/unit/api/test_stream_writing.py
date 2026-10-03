import pytest
from httpx import AsyncClient, ASGITransport
from src.backend.server import app
from src.backend.auth import get_current_user
from src.backend.database.models import User

from src.backend.routers.stream_writing import router


@pytest.mark.asyncio
async def test_stream_writing_endpoint(real_db_manager, monkeypatch):
    """SSE 執筆ストリームが happy path のフェーズを順序대로配信すること。

    エンドポイントは `UnitOfWork(AppContainer.db())` で DB を直接開き、
    `verify_book_ownership` で book_id=1 の実在と所有者を検証する
    （src/backend/routers/stream_writing.py:35-39）。したがって作品行が
    用意されないと必ず Error フェーズになる。

    `AppContainer.db` は dependency_injector の **Singleton** で、
    プロセス内で最初に呼ばれた時点で接続 URL が確定する。conftest の
    `real_db_manager` は同期 engine しか差し替えないため、
    他のテストが先に `AppContainer.db()` を起動すると
    元の DATABASE_URL に束縛されたままになり、本テストが順序依存で落ちる。

    そこで provider 自体を override して、一時 SQLite に確実に束縛し直す。
    """
    import os

    from dependency_injector import providers

    from src.backend.database.core import DatabaseManager
    from src.backend.database.models import Book
    from src.core.container import AppContainer

    transport = ASGITransport(app=app)

    # 検証対象のユーザー（id=1）
    test_user = User(id=1, email="test@example.com", hashed_password="test", display_name="testuser")

    # 一時 DB に束縛し直す（後述の順序依存を排除）
    temp_url = os.environ["DATABASE_URL"]
    AppContainer.db.override(providers.Object(DatabaseManager(temp_url)))

    session = real_db_manager
    # user_id は FK なので、依存オーバーライドで渡す objects だけでなく
    # DB 側にも User 行を作る必要がある
    session.add(test_user)
    book = Book(
        id=1,
        user_id=test_user.id,
        title="テスト作品",
        genre="ファンタジー",
        concept="テスト",
        synopsis="テストあらすじ",
        target_eps=10,
    )
    session.add(book)
    session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Ensure router is included (safe to call multiple times)
            app.include_router(router)

            # New endpoint signature: /api/stream/writing/{book_id}/{ep_num}?branch_id=1
            resp = await client.get("/api/stream/writing/1/1?branch_id=1")
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            content = resp.text
            assert "ContextBuilding" in content, f"Error phase was emitted instead: {content[:500]}"
            assert "Complete" in content
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        AppContainer.db.reset_override()
