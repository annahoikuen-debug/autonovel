"""Coverage tests for src/backend/database/repository.py (DataRepositoryFacade + BookRepository)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import src.backend.database.repository as repo_mod
from src.backend.database.models import Book
from src.backend.database.repository import BookRepository, DataRepositoryFacade
from src.backend.database.core import DatabaseManager


def test_book_repository_get():
    """BookRepository.get_book() の正常系テスト。"""
    session = MagicMock()
    repo = BookRepository(session)

    mock_book = MagicMock(spec=Book)
    mock_book.book_id = 1
    mock_book.title = "テスト小説"
    session.get.return_value = mock_book

    book = repo.get_book(1)
    assert book is mock_book
    session.get.assert_called_once_with(Book, 1)


def test_book_repository_get_none():
    """BookRepository.get_book() のNone返却テスト。"""
    session = MagicMock()
    repo = BookRepository(session)

    session.get.return_value = None

    book = repo.get_book(999)
    assert book is None
    session.get.assert_called_once_with(Book, 999)


def test_book_repository_get_with_kana():
    """BookRepository.get_book() で kana も取得できるテスト。"""
    session = MagicMock()
    repo = BookRepository(session)

    mock_book = MagicMock(spec=Book)
    mock_book.book_id = 1
    mock_book.title = "テスト小説"
    mock_book.title_kana = "てすとしょうせつ"
    session.get.return_value = mock_book

    book = repo.get_book(1)
    assert book.title_kana == "てすとしょうせつ"


def test_data_repository_facade():
    """DataRepositoryFacade の動作確認テスト。"""
    from src.backend.database.repository import DataRepositoryFacade
    from src.backend.database.core import DatabaseManager

    db = MagicMock(spec=DatabaseManager)
    facade = DataRepositoryFacade(db)

    # __getattr__ で wrapper が返るため、create_book が呼び出せるか確認
    assert hasattr(facade, "create_book")
    assert hasattr(facade, "get_book")
