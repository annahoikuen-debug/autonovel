"""リソース所有権ガード (IDOR防止)。

本モジュールが `verify_book_ownership` の唯一の実装である。
`src.backend.middleware.tenant_guard` は後方互換のため本モジュールへ委譲する。
"""
from __future__ import annotations
from typing import Any
from fastapi import HTTPException, status
from sqlalchemy import select

from src.backend.database.models import Book, User
from src.backend.database.uow import UnitOfWork
from src.core.container import AppContainer
from src.core.exceptions import NotFoundError


def _is_admin(current_user: Any) -> bool:
    """管理者ロールかどうかを判定する。"""
    return getattr(current_user, "role", "user") == "admin"


async def verify_book_ownership(
    book_id: int,
    current_user: User,
    uow: UnitOfWork | None = None,
) -> Book:
    """指定された book_id が current_user に帰属しているか検証する。

    管理者 (role == 'admin') はバイパス可能。

    。所有者 (`Book.user_id`) が未設定 (`NULL`) の作品はpermissions を持たないものとして扱い、
    管理者以外は 403 で拒否する（以前の実装は `user_id is None` の場合 access を
    許可しており、`init_db` が種として投入する `Book(id=1)` などが
    誰でも読み書きできる状態になっていた）。
    """
    async def _check(session: Any) -> Book:
        stmt = select(Book).where(Book.id == book_id)
        result = await session.execute(stmt)
        book = result.scalar_one_or_none()
        if not book:
            raise NotFoundError(f"作品が見つかりません: {book_id}", resource_type="Book", resource_id=str(book_id))

        if _is_admin(current_user):
            return book

        current_user_id = getattr(current_user, "id", None)
        # 所有者が NULL / 呼び出し側 ID が NULL の場合はいずれも拒否する
        if book.user_id is None or current_user_id is None or book.user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="この作品に対するアクセス権限がありません",
            )
        return book

    if hasattr(uow, "session") and uow.session is not None:
        return await _check(uow.session)
    if hasattr(uow, "get_session"):
        # DatabaseManager.get_session() は AsyncSession を返す（async context manager ではない）ため
        # 明示的に close する
        session = uow.get_session()
        try:
            return await _check(session)
        finally:
            await session.close()
    if hasattr(uow, "execute"):
        return await _check(uow)
    async with UnitOfWork(AppContainer.db()) as local_uow:
        return await _check(local_uow.session)


def verify_book_ownership_sync(book_id: int, current_user: User, db: Any) -> Book:
    """``verify_book_ownership`` の同期セッション版。

    ``commercial_planning`` など ``Depends(get_db)`` の同期 ``Session`` を受ける
    ルーターは非同期版をそのまま呼べない。所有権判定のロジックが二重化しないよう、
    判定部分だけを共有している。

    判定内容は ``verify_book_ownership`` と同一:
    管理者 (``role == 'admin'``) はバイパスし、所有者 ``NULL`` は拒否する。
    """
    book = db.execute(select(Book).where(Book.id == book_id)).scalar_one_or_none()
    if not book:
        raise NotFoundError(
            f"作品が見つかりません: {book_id}", resource_type="Book", resource_id=str(book_id)
        )

    if _is_admin(current_user):
        return book

    current_user_id = getattr(current_user, "id", None)
    if book.user_id is None or current_user_id is None or book.user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="この作品に対するアクセス権限がありません",
        )
    return book


__all__ = ["verify_book_ownership", "verify_book_ownership_sync"]
