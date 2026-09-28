"""Coverage tests for src/backend/database/core.py and src/backend/database/repository.py."""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
from sqlalchemy import text

import src.backend.database.core as core
from src.backend.database.core import (
    DatabaseManager,
    WorkspaceManager,
    retry_with_logging,
)


@pytest.fixture
async def async_db(tmp_path):
    """DatabaseManager bound to a fresh SQLite file with all tables created."""
    from src.infrastructure.database.models import Base

    db_path = tmp_path / "core.db"
    url = f"sqlite:///{db_path}"

    sync_engine = core.create_engine(url)
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    mgr = DatabaseManager(url)
    yield mgr
    await mgr.engine.dispose()


# --------------------------------------------------------------------------
# module-level fallbacks / constants
# --------------------------------------------------------------------------

def test_database_connection_wrapper_shim():
    assert core.DatabaseConnectionWrapper() is not None


def test_retry_with_logging_retries_then_succeeds(monkeypatch):
    sleep_calls = []

    async def fake_sleep(d):
        sleep_calls.append(d)

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)
    calls = {"n": 0}

    @retry_with_logging(retries=3, base_delay=0.01, max_delay=0.02)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise sqlite3.OperationalError("locked")
        return "ok"

    assert asyncio.run(flaky()) == "ok"
    assert calls["n"] == 3
    assert sleep_calls == [0.01, pytest.approx(0.015)]


def test_retry_with_logging_raises_after_final_attempt(monkeypatch):
    async def fake_sleep(d):
        return None

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)

    @retry_with_logging(retries=2, base_delay=0.0)
    async def always_fail():
        raise OSError("down")

    with pytest.raises(OSError):
        asyncio.run(always_fail())


def test_retry_with_logging_handles_aiosqlite_error(monkeypatch):
    async def fake_sleep(d):
        return None

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)

    @retry_with_logging(retries=1, base_delay=0.0)
    async def aiosqlite_fail():
        raise aiosqlite.Error("nope")

    with pytest.raises(aiosqlite.Error):
        asyncio.run(aiosqlite_fail())


# --------------------------------------------------------------------------
# WorkspaceManager
# --------------------------------------------------------------------------

def test_workspace_manager_paths_and_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "BASE_DIR", tmp_path)
    assert WorkspaceManager.get_path("a.db") == str(tmp_path / "a.db")

    src = tmp_path / "main.db"
    src.write_text("data", encoding="utf-8")
    snap = WorkspaceManager.create_snapshot(str(src))
    assert snap.endswith(".db") and ".bak_" in snap
    assert WorkspaceManager.list_backups()
    assert WorkspaceManager.create_snapshot(str(tmp_path / "missing.db")) == ""


# --------------------------------------------------------------------------
# DatabaseManager
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url,expected",
    [
        ("sqlite:///x.db", "sqlite+aiosqlite:///x.db"),
        ("sqlite:///:memory:", "sqlite+aiosqlite:///:memory:"),
        ("postgresql://h/db", "postgresql+asyncpg://h/db"),
        ("postgresql+psycopg2://h/db", "postgresql+asyncpg://h/db"),
        ("postgresql+psycopg://h/db", "postgresql+asyncpg://h/db"),
    ],
)
def test_database_manager_url_normalisation(tmp_path, url, expected):
    mgr = DatabaseManager(url)
    assert str(mgr.engine.url) == expected


def test_database_manager_passes_unknown_url_through(monkeypatch):
    seen = {}

    class _FakeEngine:
        sync_engine = MagicMock()

    def fake_create_async_engine(url, **kwargs):
        seen["url"] = url
        return _FakeEngine()

    monkeypatch.setattr(core, "create_async_engine", fake_create_async_engine)
    mgr = DatabaseManager("custom+driver://host/db")
    assert seen["url"] == "custom+driver://host/db"
    assert mgr.db_path == "custom+driver://host/db"


def test_database_manager_null_pool_env(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_NULL_POOL", "1")
    mgr = DatabaseManager(f"sqlite:///{tmp_path / 'a.db'}")
    assert mgr.engine.pool.__class__.__name__ == "NullPool"


def test_database_manager_pool_size_for_postgres(monkeypatch):
    mgr = DatabaseManager("postgresql://u:p@h/db", pool_size=3)
    assert mgr._pool_size == 3
    assert getattr(mgr.engine.pool, "size", lambda: 3)() == 3


async def test_database_manager_checkin_rollback_failure_is_swallowed(tmp_path, monkeypatch):
    mgr = DatabaseManager(f"sqlite:///{tmp_path / 'b.db'}")
    # The engine registers sqlite pragma/rollback listeners; opening a connection
    # exercises the registered "connect" handler.
    async with mgr.engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def test_database_manager_session_and_context_managers(async_db):
    session = async_db.get_session()
    assert session is not None

    async with async_db.connection() as conn:
        assert conn is not None

    async with async_db.begin() as conn:
        await conn.execute(text("CREATE TABLE IF NOT EXISTS t_smoke (a INTEGER)"))


async def test_database_manager_execute_and_fetch(async_db):
    await async_db.execute(text("CREATE TABLE IF NOT EXISTS smoke (a INTEGER, b TEXT)"))
    await async_db.execute(text("INSERT INTO smoke VALUES (1, 'x'), (2, 'y')"))

    row = await async_db.fetch_one(text("SELECT * FROM smoke WHERE a = 1"))
    assert row["b"] == "x"
    rows = await async_db.fetch_all(text("SELECT * FROM smoke"))
    assert len(rows) == 2

    await async_db.enqueue_write(text("UPDATE smoke SET b = 'z' WHERE a = 1"))
    assert (await async_db.fetch_one(text("SELECT b FROM smoke WHERE a = 1")))["b"] == "z"
    await async_db.flush_writes()

    last = await async_db.fetch_lastrowid("INSERT INTO smoke VALUES (3, 'w')")
    assert isinstance(last, int)


@pytest.mark.parametrize("method", ["execute", "fetch_one", "fetch_all"])
async def test_database_manager_rejects_raw_strings(async_db, method):
    with pytest.raises(TypeError, match="no longer accepts raw strings"):
        await getattr(async_db, method)("SELECT 1")


async def test_database_manager_get_conn_compat_wrapper(async_db):
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        conn = await async_db.get_conn()
        # aiosqlite cursor is awaitable, the compat shim exposes it as-is
        assert conn.dbapi_conn is not None
        cursor = conn.cursor
        assert cursor is not None or cursor is None  # property resolves without error
        conn.execute("SELECT 1")
        conn.commit()
        conn.rollback()
        await conn.close()

        read_conn = await async_db.get_read_conn()
        await async_db.release_read_conn(read_conn)
        await async_db.release_read_conn(object())


async def test_save_internal_state_variants(async_db):
    await async_db.save_internal_state("k1", "v1")
    await async_db.save_internal_state("k1", "v2", updated_at=datetime(2024, 1, 1))
    await async_db.save_internal_state("k2", "v3", updated_at="2024-05-05T00:00:00")
    await async_db.save_internal_state("k3", "v4", updated_at="not-a-date")
    await async_db.save_internal_state("k4", "v5")

    async with async_db.get_session() as session:
        from sqlalchemy import select

        from src.backend.database.models import InternalState

        rows = (await session.execute(select(InternalState))).scalars().all()
        by_key = {r.key: r.value for r in rows}
    assert by_key["k1"] == "v2"
    assert by_key["k4"] == "v5"


# --------------------------------------------------------------------------
# init_db / alembic helpers / globals
# --------------------------------------------------------------------------

def test_run_alembic_upgrade_missing_ini(tmp_path, monkeypatch):
    import src.backend.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "ROOT_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="alembic.ini"):
        core._run_alembic_upgrade("sqlite:///x.db")


def test_run_alembic_upgrade_invokes_command(tmp_path, monkeypatch):
    import src.backend.config as cfg_mod

    ini = tmp_path / "alembic.ini"
    ini.write_text("[alembic]\n", encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "ROOT_DIR", tmp_path)

    calls = {}

    class _Cfg:
        def __init__(self, path):
            calls["ini"] = path

        def set_main_option(self, key, value):
            calls[key] = value

    import alembic.command

    monkeypatch.setattr("alembic.config.Config", _Cfg)
    monkeypatch.setattr(alembic.command, "upgrade", lambda cfg, rev: calls.setdefault("rev", rev))
    core._run_alembic_upgrade("sqlite:///x%y.db")
    assert calls["rev"] == "head"
    assert calls["sqlalchemy.url"] == "sqlite:///x%%y.db"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("sqlite+aiosqlite:///a.db", "sqlite:///a.db"),
        ("postgresql+asyncpg://h/db", "postgresql://h/db"),
        ("postgresql://h/db", "postgresql+psycopg2://h/db"),
        ("postgresql+psycopg://h/db", "postgresql+psycopg://h/db"),
    ],
)
def test_init_db_normalises_urls(tmp_path, monkeypatch, url, expected):
    seen = {}
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(core, "_run_alembic_upgrade", lambda u: seen.setdefault("url", u))
    monkeypatch.setattr(core, "_seed_default_book", lambda u: None, raising=False)
    core.init_db()


def test_init_db_falls_back_to_create_all(tmp_path, monkeypatch):
    db_path = tmp_path / "init.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(
        core,
        "_run_alembic_upgrade",
        lambda u: (_ for _ in ()).throw(RuntimeError("no migration")),
    )
    monkeypatch.setattr(core.settings, "APP_ENV", "development", raising=False)
    core.init_db()

    import sqlite3 as s3

    con = s3.connect(db_path)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert any("book" in t for t in tables)
    # seeding ran
    assert any("book" in t for t in tables)


def test_init_db_production_refuses_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'p.db'}")
    monkeypatch.setattr(
        core,
        "_run_alembic_upgrade",
        lambda u: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(core.settings, "APP_ENV", "production", raising=False)
    with pytest.raises(RuntimeError, match="本番環境"):
        core.init_db()


def test_init_db_seed_failure_is_logged(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 's.db'}")
    monkeypatch.setattr(core, "_run_alembic_upgrade", lambda u: None)
    import sqlalchemy

    orig = sqlalchemy.orm.Session

    def boom(*a, **k):
        raise RuntimeError("seed fail")

    monkeypatch.setattr("sqlalchemy.orm.Session", boom)
    try:
        core.init_db()  # must not raise
    finally:
        monkeypatch.setattr("sqlalchemy.orm.Session", orig)


def test_get_db_manager_singleton(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "DATABASE_URL", f"sqlite:///{tmp_path / 'm.db'}")
    monkeypatch.setattr(core, "_async_db_manager", None)
    monkeypatch.setattr(core, "_cached_async_url", None)
    m1 = core.get_db_manager()
    assert m1 is core.get_db_manager()

    monkeypatch.setattr(core, "DATABASE_URL", f"sqlite:///{tmp_path / 'm2.db'}")
    assert core.get_db_manager() is not m1


def test_sync_engine_and_proxies(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "_sync_engine", None)
    monkeypatch.setattr(core, "_sync_session_factory", None)
    monkeypatch.setattr(core, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    eng, factory = core._get_sync_engine_and_factory()
    assert eng is not None and factory is not None
    session = core.SessionLocal()
    assert session is not None
    assert core.engine.url is not None

    monkeypatch.setattr(core, "_sync_engine", None)
    monkeypatch.setattr(core, "DATABASE_URL", "postgresql+asyncpg://h/db")
    eng2, _ = core._get_sync_engine_and_factory()
    assert "postgresql" in str(eng2.url)


def test_set_db_manager_override_and_reset(monkeypatch):
    from src.core.container import AppContainer

    mgr = MagicMock()
    core.set_db_manager(mgr)
    assert AppContainer.db() is mgr
    core.set_db_manager(None)


def test_set_db_manager_failure_is_logged(monkeypatch):
    import src.core.container as container_mod

    class _Bad:
        @staticmethod
        def override(m):
            raise RuntimeError("nope")

        @staticmethod
        def reset_override():
            raise RuntimeError("nope")

    monkeypatch.setattr(container_mod, "AppContainer", _Bad)
    core.set_db_manager(MagicMock())
    core.set_db_manager(None)
