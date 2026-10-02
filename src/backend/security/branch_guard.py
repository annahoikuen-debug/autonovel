"""ブランチ所有権ガード (branches.py の cross-tenant 防止)。

``branch_id`` は 1 が全作品の既定値なので、「request が本人の作品である」だけでは不十分。
``episodes.py`` の ``_verify_branch_belongs_to_book`` が持っていたロジックを
本モジュールへ移し、``branches.py`` からも利用する。
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select

from src.backend.database.models import Book, Branch


async def verify_branch_belongs_to_book(
    uow: Any, book_id: int, branch_id: int
) -> None:
    """``branch_id`` が検証済み ``book_id`` に属するかを確認する。

    乖離があれば 403。``branch_id == 1``（全作品の既定ブランチ）の場合は
    ``books.current_branch_id`` が別ブランチを指していないことを確認する。
    """
    if branch_id == 1:
        book = await uow.books.get_book(book_id) if hasattr(uow, "books") else None
        current = getattr(book, "current_branch_id", None) if book else None
        if current is not None and current != 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="指定ブランチはこの作品に属していません",
            )
        return

    session = getattr(uow, "session", uow)
    owner = await session.scalar(
        select(Book.id).where(Branch.book_id == book_id).where(Branch.id == branch_id)
    )
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="指定ブランチはこの作品に属していません",
        )


__all__ = ["verify_branch_belongs_to_book"]
