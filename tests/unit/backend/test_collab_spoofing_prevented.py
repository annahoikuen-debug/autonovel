import pytest
from fastapi import HTTPException
from src.backend.database.models import Book, ProjectMember, User
from src.backend.routers.collab import _verify_book_access


class MockCollabRepo:
    def __init__(self, members: list[ProjectMember]):
        self._members = members

    async def list_members(self, book_id: int):
        return [m for m in self._members if m.book_id == book_id]


class MockBookRepo:
    def __init__(self, book: Book | None):
        self._book = book

    async def get_book(self, book_id: int):
        return self._book


class MockUoW:
    def __init__(self, book: Book | None, members: list[ProjectMember]):
        self.books = MockBookRepo(book)
        self.collab = MockCollabRepo(members)


@pytest.mark.asyncio
async def test_display_name_spoofing_is_rejected():
    """
    攻撃者が正規メンバーと同一の display_name を騙っても、
    email / user_id が一致しなければ 403 で拒絶されること。
    """
    book = Book(id=1, user_id=10, title="Collaborative Novel")
    # 正規メンバー: user_name="alice@example.com"
    members = [ProjectMember(id=1, book_id=1, user_name="alice@example.com", role="editor")]
    uow = MockUoW(book, members)

    # 攻撃者: display_name="alice@example.com" だが email は "attacker@evil.com"
    attacker = User(
        id=99,
        role="user",
        email="attacker@evil.com",
        display_name="alice@example.com",
    )

    with pytest.raises(HTTPException) as exc_info:
        await _verify_book_access(uow, 1, attacker)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_legitimate_member_by_email_is_allowed():
    """正規メンバーが登録済み email でアクセスした場合は許可されること。"""
    book = Book(id=1, user_id=10, title="Collaborative Novel")
    members = [ProjectMember(id=1, book_id=1, user_name="alice@example.com", role="editor")]
    uow = MockUoW(book, members)

    legit_user = User(
        id=20,
        role="user",
        email="alice@example.com",
        display_name="Alice Wonderland",
    )

    # 例外なく通過すること
    await _verify_book_access(uow, 1, legit_user)


@pytest.mark.asyncio
async def test_legitimate_member_by_user_id_is_allowed():
    """正規メンバーが登録済み user_id でアクセスした場合は許可されること。"""
    book = Book(id=1, user_id=10, title="Collaborative Novel")
    members = [ProjectMember(id=2, book_id=1, user_name="25", role="editor")]
    uow = MockUoW(book, members)

    legit_user = User(
        id=25,
        role="user",
        email="bob@example.com",
        display_name="Bob",
    )

    # 例外なく通過すること
    await _verify_book_access(uow, 1, legit_user)
