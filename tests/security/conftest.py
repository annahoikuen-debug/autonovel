"""セキュリティテスト用の共有フィクスチャ。

make_user / authenticate / create_book_for_user は
tests/security 配下の IDOR・所有権検証テストで共通利用する。
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.backend.database.repositories import BookRepository  # 実装パスに合わせて調整


def make_user(email: str = "user@example.com") -> Any:
    """テスト用ユーザーを作成（DB またはモック）。実装はプロジェクトの user_factory に合わせる。"""
    user = MagicMock()
    user.id = abs(hash(email)) % 100000
    user.email = email
    user.role = "user"
    user.status = "active"
    return user


def authenticate(user: Any) -> str:
    """ユーザーの JWT またはテスト用トークン文字列を返す。"""
    return f"test-token-{user.id}"


def create_book_for_user(user: Any, title: str = "Test Book") -> Any:
    """ユーザー所有の本を作成し、book オブジェクト（.id を持つ）を返す。"""
    book = MagicMock()
    book.id = abs(hash((user.id, title))) % 100000
    book.title = title
    book.user_id = user.id
    book.genre = "fantasy"
    return book


@pytest.fixture
def owner_user():
    return make_user("owner@example.com")


@pytest.fixture
def victim_user():
    return make_user("victim@example.com")


@pytest.fixture
def owner_book(owner_user):
    return create_book_for_user(owner_user, title="Victim Book")
