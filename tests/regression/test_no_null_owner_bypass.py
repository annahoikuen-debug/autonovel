import pytest
from fastapi import HTTPException
from src.backend.database.models import Book, User
from src.backend.security.owner_guard import verify_book_ownership, verify_book_ownership_sync


class DummySession:
    def __init__(self, book: Book | None):
        self._book = book

    async def execute(self, stmt):
        class Result:
            def __init__(self, b):
                self._b = b

            def scalar_one_or_none(self):
                return self._b

        return Result(self._book)

    def scalar_one_or_none(self):
        return self._book


class DummySyncSession:
    def __init__(self, book: Book | None):
        self._book = book

    def execute(self, stmt):
        class Result:
            def __init__(self, b):
                self._b = b

            def scalar_one_or_none(self):
                return self._b

        return Result(self._book)


@pytest.mark.asyncio
async def test_verify_book_ownership_null_user_id_rejected_for_regular_user():
    """所有者 user_id が NULL の作品は一般ユーザーに対して 403 で拒否されること。"""
    null_owner_book = Book(id=999, user_id=None, title="Orphan Book")
    dummy_session = DummySession(null_owner_book)
    normal_user = User(id=10, role="user", email="user@example.com", display_name="User 10")

    with pytest.raises(HTTPException) as exc_info:
        await verify_book_ownership(999, normal_user, uow=dummy_session)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_verify_book_ownership_null_user_id_allowed_for_admin():
    """所有者 user_id が NULL の作品でも管理者はアクセス可能であること。"""
    null_owner_book = Book(id=999, user_id=None, title="Orphan Book")
    dummy_session = DummySession(null_owner_book)
    admin_user = User(id=1, role="admin", email="admin@example.com", display_name="Admin")

    res = await verify_book_ownership(999, admin_user, uow=dummy_session)
    assert res.id == 999


@pytest.mark.asyncio
async def test_verify_book_ownership_mismatched_owner_rejected():
    """他人の作品は 403 で拒否されること。"""
    other_book = Book(id=100, user_id=99, title="Other Book")
    dummy_session = DummySession(other_book)
    normal_user = User(id=10, role="user", email="user@example.com", display_name="User 10")

    with pytest.raises(HTTPException) as exc_info:
        await verify_book_ownership(100, normal_user, uow=dummy_session)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_verify_book_ownership_matched_owner_allowed():
    """自身の作品は正常にアクセスできること。"""
    my_book = Book(id=100, user_id=10, title="My Book")
    dummy_session = DummySession(my_book)
    normal_user = User(id=10, role="user", email="user@example.com", display_name="User 10")

    res = await verify_book_ownership(100, normal_user, uow=dummy_session)
    assert res.id == 100
    assert res.user_id == 10


def test_verify_book_ownership_sync_null_user_id_rejected():
    """同期版でも所有者 user_id が NULL の作品は 403 で拒否されること。"""
    null_owner_book = Book(id=999, user_id=None, title="Orphan Book")
    dummy_session = DummySyncSession(null_owner_book)
    normal_user = User(id=10, role="user", email="user@example.com", display_name="User 10")

    with pytest.raises(HTTPException) as exc_info:
        verify_book_ownership_sync(999, normal_user, dummy_session)
    assert exc_info.value.status_code == 403
