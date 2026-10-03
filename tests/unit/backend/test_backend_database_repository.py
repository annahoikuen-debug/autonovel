"""Coverage tests for src/backend/database/repository.py (DataRepositoryFacade + BookRepository)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import src.backend.database.repository as repo_mod
from src.backend.database.core import DatabaseManager
from src.backend.database.models import Book, Character, Chapter, InternalState
from src.backend.database.repository import (
    BookRepository,
    DataRepository,
    DataRepositoryFacade,
)
from src.backend.database.uow_context import current_uow


@pytest.fixture
def sync_session(tmp_path):
    """A real synchronous Session with all tables created."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src.infrastructure.database.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
async def async_session(tmp_path):
    """A real AsyncSession with all tables created."""
    from src.infrastructure.database.models import Base

    from src.backend.database import core as core_mod

    url = f"sqlite:///{tmp_path / 'arepo.db'}"
    sync_engine = core_mod.create_engine(url)
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    mgr = DatabaseManager(url)
    session = mgr.get_session()
    yield session, mgr
    await session.close()
    await mgr.engine.dispose()


# --------------------------------------------------------------------------
# DataRepositoryFacade
# --------------------------------------------------------------------------

def test_facade_is_aliased():
    assert DataRepository is DataRepositoryFacade


async def test_facade_delegates_through_uow():
    books_repo = MagicMock()
    books_repo.get_book = AsyncMock(return_value="via-uow")
    uow = MagicMock()
    uow.books = books_repo

    token = current_uow.set(uow)
    try:
        facade = DataRepositoryFacade(MagicMock())
        assert await facade.get_book(1) == "via-uow"
    finally:
        current_uow.reset(token)


async def test_facade_raises_for_unknown_attr_in_uow_mode():
    uow = MagicMock()
    for attr in (
        "books", "plots", "chapters", "characters", "branches", "bible",
        "misc", "rules", "audit", "prompt_versions", "illustrations",
    ):
        setattr(uow, attr, MagicMock(spec=[]))

    token = current_uow.set(uow)
    try:
        facade = DataRepositoryFacade(MagicMock())
        with pytest.raises(AttributeError, match="UoW mode"):
            await facade.does_not_exist()
    finally:
        current_uow.reset(token)


async def test_facade_auto_mode_fallback(monkeypatch):
    class _FakeUow:
        def __init__(self, db):
            self.db = db

        async def __aenter__(self):
            repo = MagicMock()
            repo.get_book = AsyncMock(return_value="auto")
            self.books = repo
            return self

        async def __aexit__(self, *a):
            return False

    import src.backend.database.uow as uow_mod

    monkeypatch.setattr(uow_mod, "UnitOfWork", _FakeUow)
    token = current_uow.set(None)
    try:
        facade = DataRepositoryFacade(MagicMock())
        assert await facade.get_book(3) == "auto"
    finally:
        current_uow.reset(token)


async def test_facade_auto_mode_unknown_attr(monkeypatch):
    class _FakeUow:
        def __init__(self, db):
            pass

        async def __aenter__(self):
            for attr in (
                "books", "plots", "chapters", "characters", "branches", "bible",
                "misc", "rules", "audit", "prompt_versions",
            ):
                setattr(self, attr, MagicMock(spec=[]))
            return self

        async def __aexit__(self, *a):
            return False

    import src.backend.database.uow as uow_mod

    monkeypatch.setattr(uow_mod, "UnitOfWork", _FakeUow)
    token = current_uow.set(None)
    try:
        facade = DataRepositoryFacade(MagicMock())
        with pytest.raises(AttributeError, match="Auto mode"):
            await facade.nope()
    finally:
        current_uow.reset(token)


async def test_facade_get_state_and_set_state(async_session):
    session, mgr = async_session
    facade = DataRepositoryFacade(mgr)

    assert await facade.get_state("missing", default="fallback") == "fallback"

    await facade.set_state("k", {"a": 1})
    assert await facade.get_state("k") == {"a": 1}

    await facade.set_state("k", "raw-string")
    assert await facade.get_state("k") == "raw-string"

    # unparsable JSON falls back to the raw stored value
    session.add(InternalState(key="bad", value="{not json"))
    await session.commit()
    assert await facade.get_state("bad") == "{not json"


# --------------------------------------------------------------------------
# BookRepository - construction / sync helpers
# --------------------------------------------------------------------------

def test_book_repository_construction_variants(sync_session):
    r1 = BookRepository(sync_session)
    assert r1.session is sync_session
    assert r1._db is None
    assert r1.is_async is False

    r2 = BookRepository()
    assert r2.session is not None
    r2.session.close()

    r3 = BookRepository(123)
    assert r3.session is not None
    r3.session.close()

    r4 = BookRepository(DatabaseManager("sqlite:///x.db"))
    assert r4._db is not None
    r4.session.close()


async def test_commit_and_refresh_helpers(sync_session):
    repo = BookRepository(sync_session)
    await repo.commit_async()
    assert repo.is_async is False
    book = Book(title="t", genre="g", concept="c", synopsis="s", target_eps=1)
    sync_session.add(book)
    await repo.commit_async()
    await repo.refresh_async(book)


async def test_commit_and_refresh_helpers_async(async_session):
    session, mgr = async_session
    repo = BookRepository(session)
    assert repo.is_async is True
    book = Book(title="t", genre="g", concept="c", synopsis="s", target_eps=1)
    session.add(book)
    await repo.commit_async()
    await repo.refresh_async(book)


def test_safe_commit_with_awaitable(sync_session, monkeypatch):
    repo = BookRepository(sync_session)

    class _AwaitableCommit:
        def __await__(self):
            async def _run():
                return None

            return _run().__await__()

    monkeypatch.setattr(sync_session, "commit", lambda: _AwaitableCommit())
    # no running loop -> asyncio.run path
    repo._safe_commit()


def test_safe_commit_with_awaitable_inside_loop(sync_session, monkeypatch):
    import asyncio

    async def _inner():
        return None

    async def _run():
        repo = BookRepository(sync_session)
        monkeypatch.setattr(sync_session, "commit", _inner)
        repo._safe_commit()
        await asyncio.sleep(0)

    asyncio.run(_run())


def test_safe_refresh_with_awaitable(sync_session, monkeypatch):
    repo = BookRepository(sync_session)
    instance = Book()

    class _AwaitableRefresh:
        def __await__(self):
            async def _inner():
                return None

            return _inner().__await__()

    monkeypatch.setattr(sync_session, "refresh", lambda i: _AwaitableRefresh())
    repo._safe_refresh(instance)


# --------------------------------------------------------------------------
# BookRepository - tasks
# --------------------------------------------------------------------------

def test_task_lifecycle_sync(sync_session):
    repo = BookRepository(sync_session)
    task = repo.create_task(task_id="t1", status="pending")
    assert repo.get_task("t1") is task
    assert repo.get_task("missing") is None

    repo.update_task_status("t1", "running")
    assert repo.get_task("t1").status == "running"
    repo.update_task_status("missing", "done")

    repo.set_task_result("t1", "payload")
    assert repo.get_task("t1").status == "completed"
    assert repo.get_task("t1").result == "payload"
    repo.set_task_result("missing", "x")

    # autogenerated id
    auto = repo.create_task()
    assert auto.id

    repo.delete_task("t1")
    assert repo.get_task("t1") is None
    repo.delete_task("t1")


async def test_task_lifecycle_async(async_session):
    session, mgr = async_session
    repo = BookRepository(session)
    task = await repo.create_task_async(task_id="a1")
    assert (await repo.get_task_async("a1")) is task
    await repo.update_task_status_async("a1", "running")
    assert (await repo.get_task_async("a1")).status == "running"
    await repo.update_task_status_async("missing", "x")
    await repo.set_task_result_async("a1", "done")
    assert (await repo.get_task_async("a1")).status == "completed"
    await repo.set_task_result_async("missing", "x")
    await repo.create_task_async()
    await repo.delete_task_async("a1")
    assert await repo.get_task_async("a1") is None
    await repo.delete_task_async("a1")


def test_get_book_sync_and_queries(sync_session):
    repo = BookRepository(sync_session)
    book = repo.save_or_update_book_with_chapter(
        book_id=None, title="B", chapter_text="hello", character_params={"name": "Hero", "personality": "brave", "ability": "sword"}
    )
    assert repo.get_book(book.id).title == "B"

    book2 = repo.save_or_update_book_with_chapter(book_id=book.id, chapter_text="second")
    assert book2.id == book.id

    # non-existent book_id creates a new book
    book3 = repo.save_or_update_book_with_chapter(book_id=999999, title="New")
    assert book3.id != 999999

    chapters = repo.get_all_non_anchor_chapters(book.id)
    assert len(chapters) >= 1
    assert repo.get_all_non_anchor_chapters(book.id, order_by="created_at") is not None

    chars = repo.get_all_characters(book.id)
    assert [c.name for c in chars] == ["Hero"]

    assert repo.get_latest_bible(book.id) is None
    assert repo.get_all_plots(book.id, branch_id=1) == []


def test_save_or_update_updates_existing_chapter_and_character(sync_session):
    repo = BookRepository(sync_session)
    book = repo.save_or_update_book_with_chapter(
        book_id=None, chapter_text="first", character_params={"name": "A"}
    )
    repo.save_or_update_book_with_chapter(
        book_id=book.id, chapter_text="updated", character_params={"name": "A", "personality": "calm", "ability": "magic"}
    )
    chapter = sync_session.query(Chapter).filter_by(book_id=book.id, ep_num=1).one()
    assert chapter.content == "updated"
    char = sync_session.query(Character).filter_by(book_id=book.id, name="A").one()
    assert char.personality == "calm"
    assert char.ability == "magic"


def test_save_or_update_without_chapter_text_or_character(sync_session):
    repo = BookRepository(sync_session)
    book = repo.save_or_update_book_with_chapter(book_id=0, chapter_text="", character_params=None)
    assert book.id is not None
    assert sync_session.query(Chapter).count() == 0
    book2 = repo.save_or_update_book_with_chapter(book_id=book.id, character_params={"noname": 1})
    assert book2.id == book.id


async def test_save_or_update_async(async_session):
    session, mgr = async_session
    repo = BookRepository(session)
    book = await repo.save_or_update_book_with_chapter_async(
        book_id=None, title="AB", chapter_text="text", character_params={"name": "Z", "personality": "p", "ability": "a"}
    )
    assert book.id is not None

    same = await repo.save_or_update_book_with_chapter_async(book_id=book.id, chapter_text="text2", character_params={"name": "Z", "personality": "p2", "ability": "a2"})
    assert same.id == book.id

    other = await repo.save_or_update_book_with_chapter_async(book_id=999998, title="Missing")
    assert other.id != 999998

    empty = await repo.save_or_update_book_with_chapter_async(book_id=None, chapter_text="", character_params={})
    assert empty.id is not None


async def test_book_async_get_helpers(sync_session):
    repo = BookRepository(sync_session)
    book = repo.save_or_update_book_with_chapter(book_id=None)
    got = await repo.get_book_async(book.id)
    assert got.id == book.id


def test_repository_module_exports():
    for name in (
        "AuditRepository", "BibleRepository", "AsyncBookRepository",
        "ChapterRepository", "CharacterRepository", "PlotRepository",
        "NarrativeMetricRepository",
    ):
        assert hasattr(repo_mod, name)
