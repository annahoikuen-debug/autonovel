"""P0 セキュリティ IDOR ガード網羅検証テスト"""
import pytest
from fastapi.testclient import TestClient
from src.backend.server import app
from src.backend.security.jwt import create_access_token
from src.backend.database.models import Base, User, Book
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.backend.database import get_db
from src.core.container import AppContainer

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session

@pytest.fixture(autouse=True)
async def setup_db(monkeypatch):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # conftest.py が全テストに AUTH_DISABLED=true を適用するため、
    # 認証・認可（所有権検証）経路を検証する本テストでは明示的に無効化する。
    # JWT_SECRET_KEY も固定する（実装は未設定時にプロセス毎のエフェメラルキーを
    # 生成するため、テストモジュールとアプリで鍵が分離して署名検証が必ず失敗する）。
    from src.backend.config import settings

    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test-jwt-secret-key-for-idor-regression-32bytes")
    # AppContainer.db は Singleton で順序依存を起こすため provider 単位で束縛する
    monkeypatch.setattr(AppContainer, "db", staticmethod(TestingSessionLocal), raising=False)
    # `get_current_user` / `verify_book_ownership` が使う非同期セッションも
    # テスト用 DB へ束縛する（本番 DB に接続しに行かないようにする）
    from src.backend.database import get_async_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_async_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_async_db, None)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

def test_unauthenticated_export_blocked():
    with TestClient(app) as client:
        resp = client.get("/api/export/books/1")
        assert resp.status_code == 401

def test_cross_user_book_export_forbidden():
    # Create test data: book owned by user 101
    import asyncio
    async def create_data():
        async with TestingSessionLocal() as session:
            # Create users with tenant_id = NULL (allowed)
            # `get_current_user` は `status == "active"` のユーザーのみ受理するため必須
            user_a = User(id=101, email="a@test.com", hashed_password="hash", display_name="User A", role="user", tenant_id=None, status="active")
            user_b = User(id=202, email="b@test.com", hashed_password="hash", display_name="User B", role="user", tenant_id=None, status="active")
            session.add_all([user_a, user_b])
            await session.commit()
            await session.refresh(user_a)
            await session.refresh(user_b)
            book = Book(id=1, user_id=101, title="Test Book")
            session.add(book)
            await session.commit()
            await session.refresh(book)
    asyncio.run(create_data())

    # create_access_token の契約（user_id / role キーワード）に合わせる
    token_b = create_access_token(user_id=202, role="user")
    with TestClient(app) as client:
        resp = client.get(
            "/api/export/books/1",
            headers={"Authorization": f"Bearer {token_b}"}
        )
        assert resp.status_code in [403, 404]
