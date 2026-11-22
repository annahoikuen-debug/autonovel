"""Step 1 (C1): POST /easy_mode/export-with-data の認証＋所有権検証。

C1: `easy_mode.py:633-710` は get_current_user / verify_book_ownership を欠き、
任意の book_id で他人の本（タイトル・ジャンル・本文）を上書き可。
修正後、両方を満たさないリクエストは拒否される。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.backend.server import app

client = TestClient(app)


def _override_auth(is_owner: bool):
    """認証依存をモックに差し替える。

    NOTE: `verify_book_ownership` はハンドラ本体から直接呼ばれるため
    dependency_overrides では差し替えられない（過去の `fake_verify` 上書きは
    実行されていなかった）。ガード自体は実物を実行し、`_isolated_guard_db`
    フィクスチャが用意するテスト用 DB で判定される。
    """

    async def fake_get_current_user():
        user = MagicMock()
        user.id = 100 if is_owner else 200
        user.email = "owner@example.com" if is_owner else "victim@example.com"
        user.role = "user"
        user.status = "active"
        return user

    app.dependency_overrides[src_get_current_user] = fake_get_current_user


def _clear_overrides():
    app.dependency_overrides.clear()


import src.backend.auth as auth_mod

src_get_current_user = auth_mod.get_current_user


@pytest.fixture(autouse=True)
def _isolated_guard_db(tmp_path):
    """ガード (verify_book_ownership) が参照する DB をテスト専用 SQLite に隔離する。

    ガードは `AppContainer.db()` のシングルトンで自身の UnitOfWork を開くため、
    何も差し替えないと dev の storage DB（または CI の空 DB）を見に行く。
    以前はローカルの残留データ（所有者 NULL の Book(id=1)）に偶然依存して
    403 を返していたが、クリーン環境では 404/500 で赤になる。
    ここでは「他者 (id=300) が所有する Book(id=1)」を実 DB に seed し、
    非所有ユーザー (id=200) のリクエストがガードの 403 パスで拒否されることを
    環境非依存に検証する。
    """
    import asyncio

    from sqlalchemy import create_engine
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import src.core.container as container_mod
    from src.backend.database.models import Book, User
    from src.core.container import AppContainer
    from src.infrastructure.database.models.base_orm import Base

    db_path = tmp_path / "guard_owner.db"
    sync_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(sync_engine)

    session = sessionmaker(bind=sync_engine)()
    session.add(
        User(
            id=300,
            email="other-owner@example.com",
            hashed_password="seed",
            display_name="Other Owner",
            role="user",
            status="active",
        )
    )
    session.add(Book(id=1, user_id=300, title="他人の本", genre="テスト", mode="easy"))
    session.commit()
    session.close()

    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async_session_factory = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

    original_db_provider = AppContainer.db
    container_mod.AppContainer.db = async_session_factory
    AppContainer.db = async_session_factory
    yield
    container_mod.AppContainer.db = original_db_provider
    AppContainer.db = original_db_provider
    asyncio.run(async_engine.dispose())
    sync_engine.dispose()


@pytest.fixture(autouse=True)
def _clean_overrides():
    yield
    _clear_overrides()


def test_export_with_data_rejects_unauthenticated_when_dependency_added():
    """C1: 認証済み非所有ユーザー（id=200, 非admin）のリクエストは
    実 verify_book_ownership により 403 で拒否される。

    NOTE: get_current_user のみ dependency_overrides で差し替え可能（Depends 経由）。
    未認証状態そのものは AUTH_DISABLED=true 環境では構成できないため、
    「最小権限（非admin・非所有者）」を再現して拒否パスを検証する。
    """
    _override_auth(is_owner=False)
    # NOTE: ExportRequestPayload には book_id フィールドがなく、ボディの book_id は無視される。
    # 所有権判定はクエリパラメータ book_id（seed した User(300) 所有の Book(id=1)）で行われる。
    resp = client.post(
        "/easy_mode/export-with-data?book_id=1",
        json={"title": "x", "genre": "x", "current_text": "x"},
    )
    assert resp.status_code == 403


def test_export_with_data_rejects_cross_tenant():
    """C1: 他人の book_id は所有権検証で 403。

    NOTE: 所有権判定はクエリパラメータ book_id で行われる
    （User(300) 所有の Book(id=1) に対して User(200) が要求 → 403）。
    """
    _override_auth(is_owner=False)
    resp = client.post(
        "/easy_mode/export-with-data?book_id=1",
        json={"title": "Hacked", "genre": "x", "current_text": "x"},
    )
    assert resp.status_code == 403


def test_endpoint_source_calls_verify_book_ownership():
    """C1: easy_mode.py の export_with_data_endpoint が verify_book_ownership を呼ぶ（source検査）。"""
    import inspect
    from src.backend.routers import easy_mode

    src = inspect.getsource(easy_mode.export_with_data_endpoint)
    assert "verify_book_ownership" in src, "export_with_data_endpoint に verify_book_ownership がない"
    assert "get_current_user" in src or "current_user" in src, "認証依存が無い"
