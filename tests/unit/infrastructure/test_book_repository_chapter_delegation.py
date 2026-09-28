"""tests/unit/infrastructure/test_book_repository_chapter_delegation.py.

v5.3 / C0: 執筆エージェント（`WritingAgent` / `EpisodeWriter`）には
`BookRepository` 1 つしか注入されない（`generation_tasks.py:151`）ため、
章操作と聖書読み出しが `BookRepository` から提供されていなければ
本番執筆が `AttributeError` で失敗する。

本テストは委譲メソッドの存在と委譲先の委譲を検証する。
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 循環インポートを避けるため、database パッケージを先に読み込む
import src.backend.database  # noqa: F401


DELEGATED = ("save_chapter", "get_chapter", "update_chapter_content", "get_latest_bible")


class TestBookRepositoryChapterContract:
    def test_all_delegated_methods_exist(self) -> None:
        from src.infrastructure.repositories.book import BookRepository

        for name in DELEGATED:
            assert hasattr(BookRepository, name), f"BookRepository に {name} が無い"

    def test_delegated_methods_are_async(self) -> None:
        from src.infrastructure.repositories.book import BookRepository

        for name in DELEGATED:
            fn = getattr(BookRepository, name)
            assert inspect.iscoroutinefunction(fn), f"{name} が async ではない"

    def test_save_chapter_signature_accepts_generator_call(self) -> None:
        """`generator.py` の呼び出し引数（位置引数）を全て受け付けること。"""
        from src.infrastructure.repositories.book import BookRepository

        params = inspect.signature(BookRepository.save_chapter).parameters
        for required in ("book_id", "branch_id", "ep_num", "title", "content"):
            assert required in params, f"save_chapter に {required} が無い"
            assert params[required].default is inspect.Parameter.empty, (
                f"save_chapter の {required} は必須引数であるべき"
            )

    def test_get_chapter_signature_matches_call_sites(self) -> None:
        """`agent.py:126` は `get_chapter(branch_id, end_ep)` と呼ぶ。"""
        from src.infrastructure.repositories.book import BookRepository

        params = [
            name
            for name in inspect.signature(BookRepository.get_chapter).parameters
            if name != "self"
        ]
        assert params == ["branch_id", "ep_num"], f"引数順が呼び出し側と不一致: {params}"


class TestDelegationTargets:
    def test_save_chapter_delegates_to_chapter_repository(self) -> None:
        from src.infrastructure.repositories.book import BookRepository

        repo = BookRepository.__new__(BookRepository)
        repo.session = MagicMock()
        chapter_repo = MagicMock()
        chapter_repo.create_chapter = AsyncMock(return_value=None)
        repo._chapter_repo = MagicMock(return_value=chapter_repo)  # type: ignore[method-assign]

        import asyncio

        asyncio.run(
            repo.save_chapter(
                book_id=1, branch_id=2, ep_num=3, title="第3話", content="本文"
            )
        )

        chapter_repo.create_chapter.assert_awaited_once()
        kwargs = chapter_repo.create_chapter.await_args.kwargs
        assert kwargs["book_id"] == 1
        assert kwargs["branch_id"] == 2
        assert kwargs["ep_num"] == 3
        assert kwargs["content"] == "本文"

    def test_get_chapter_delegates(self) -> None:
        from src.infrastructure.repositories.book import BookRepository

        repo = BookRepository.__new__(BookRepository)
        repo.session = MagicMock()
        chapter_repo = MagicMock()
        chapter_repo.get_chapter = AsyncMock(return_value="SENTINEL")
        repo._chapter_repo = MagicMock(return_value=chapter_repo)  # type: ignore[method-assign]

        import asyncio

        assert asyncio.run(repo.get_chapter(branch_id=2, ep_num=5)) == "SENTINEL"

    def test_get_latest_bible_delegates_to_bible_repository(self) -> None:
        from src.infrastructure.repositories.book import BookRepository

        repo = BookRepository.__new__(BookRepository)
        repo.session = MagicMock()
        bible_repo = MagicMock()
        bible_repo.get_latest_bible = AsyncMock(return_value="BIBLE")
        repo._bible_repo = MagicMock(return_value=bible_repo)  # type: ignore[method-assign]

        import asyncio

        assert asyncio.run(repo.get_latest_bible(7)) == "BIBLE"

    def test_save_chapter_generates_summary_when_missing(self) -> None:
        """summary 未指定時は本文冒頭から自動生成される（None を入れない）。"""
        from src.infrastructure.repositories.book import BookRepository

        repo = BookRepository.__new__(BookRepository)
        repo.session = MagicMock()
        chapter_repo = MagicMock()
        chapter_repo.create_chapter = AsyncMock(return_value=None)
        repo._chapter_repo = MagicMock(return_value=chapter_repo)  # type: ignore[method-assign]

        import asyncio

        content = "あ" * 500
        asyncio.run(
            repo.save_chapter(
                book_id=1, branch_id=1, ep_num=1, title="t", content=content
            )
        )
        kwargs = chapter_repo.create_chapter.await_args.kwargs
        assert kwargs["summary"], "summary が空文字になった"
        assert len(kwargs["summary"]) <= 200


class TestNoCircularImport:
    def test_lazy_import_inside_methods(self) -> None:
        """章リポジトリの import はメソッド内遅延であること（循環インポート防止）。"""
        from src.infrastructure.repositories.book import BookRepository

        src = inspect.getsource(BookRepository)
        module_level = [
            line
            for line in src.splitlines()
            if line.startswith("from src.infrastructure.repositories.chapter")
            or line.startswith("from src.infrastructure.repositories.bible")
        ]
        assert not module_level, (
            f"リポジトリの import がモジュール直下にある（循環インポート）: {module_level}"
        )
