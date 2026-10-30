"""Book repository application port.

`BookUseCases` などのアプリケーション層ユースケースが、旧レイアウトの
`src.backend.database.repositories.BookRepository` に直接依存せず、
本ポート経由で書籍リポジトリ操作を利用するためのインターフェース。

実装はインフラ層（`src.backend` 等）が注入する。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IBookRepository(Protocol):
    """書籍リポジトリのポート。"""

    async def get_all_books(self, user_id: int) -> list[Any]:
        """ユーザーの全作品を取得する。"""
        ...

    async def get_book(self, book_id: int, user_id: int) -> Any | None:
        """指定IDの作品を取得（所有権検証付き）。見つからなければ None。"""
        ...

    async def get_book_by_id(self, book_id: int) -> Any | None:
        """指定IDの作品を取得（所有権検証なし）。見つからなければ None。"""
        ...

    async def create_book(
        self,
        user_id: int,
        title: str,
        genre: str,
        concept: str,
        synopsis: str,
        target_eps: int,
        style_dna: dict,
        marketing_data: dict,
    ) -> int:
        """新規作品を作成し、生成された book_id を返す。"""
        ...

    async def delete_book(self, book_id: int, user_id: int) -> None:
        """作品を削除する。"""
        ...
