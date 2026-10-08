"""
routers/collab.py - 共同執筆・レビューコメント API

メンバー管理・章へのコメント投稿・解決マークを提供する。
コメント更新は SSE でリアルタイム配信する（簡易実装：ポーリング代替）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.backend.auth import get_current_user
from src.backend.database.models import User
from src.backend.database.uow import UnitOfWork
from src.core.container import AppContainer

router = APIRouter(prefix="/api/collab", tags=["collab"])


class MemberRequest(BaseModel):
    user_name: str
    role: str = "viewer"  # owner | editor | viewer


class CommentRequest(BaseModel):
    author_name: str
    content: str
    anchor_text: str = ""
    parent_id: int | None = None


async def _verify_book_access(uow: UnitOfWork, book_id: int, current_user: User) -> None:
    """
    リクエストのユーザーがブックの所有者または管理者であることを検証する。

    `book.user_id` が NULL (所有者未設定) の作品は「誰でもアクセス可能」にはならない。
    fail-closed: 所有者が NULL の場合は管理者および明示的なコラボレーションメンバーのみ許可し、
    それ以外は 403 で拒否する（NULL owner fall-through 脆弱性の撲滅）。
    """
    book = await uow.books.get_book(book_id)
    if not book:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Book not found", resource_type="Book", resource_id=str(book_id))

    if current_user.role == "admin":
        return

    if book.user_id == current_user.id:
        return

    # メンバーリストに含まれるかを確認（所有者以外はメンバーのみ許可）。
    # `user_id is None` の場合もここに到達し、メンバーでなければ 403 になる。
    members = await uow.collab.list_members(book_id)
    member_names = {m.user_name for m in members}
    if current_user.display_name not in member_names and current_user.email not in member_names:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="この作品へのアクセス権限がありません",
        )


# ---- Members ----
@router.post("/books/{book_id}/members")
async def add_member(
    book_id: int,
    req: MemberRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with UnitOfWork(AppContainer.db()) as uow:
        await _verify_book_access(uow, book_id, current_user)
        mid = await uow.collab.add_member(book_id, req.user_name, req.role)
    return {"status": "success", "id": mid}


@router.get("/books/{book_id}/members")
async def list_members(
    book_id: int,
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with UnitOfWork(AppContainer.db()) as uow:
        await _verify_book_access(uow, book_id, current_user)
        members = await uow.collab.list_members(book_id)
    return [
        {"id": m.id, "user_name": m.user_name, "role": m.role, "invited_at": str(m.invited_at)}
        for m in members
    ]


@router.delete("/books/{book_id}/members/{member_id}")
async def remove_member(
    book_id: int,
    member_id: int,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with UnitOfWork(AppContainer.db()) as uow:
        await _verify_book_access(uow, book_id, current_user)
        n = await uow.collab.remove_member(member_id)
    if n == 0:
        from src.core.exceptions import NotFoundError

        raise NotFoundError(
            "Member not found", resource_type="ProjectMember", resource_id=str(member_id)
        )
    return {"status": "success", "id": member_id}


# ---- Comments ----
@router.post("/books/{book_id}/chapters/{chapter_ep}/comments")
async def add_comment(
    book_id: int,
    chapter_ep: int,
    req: CommentRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with UnitOfWork(AppContainer.db()) as uow:
        await _verify_book_access(uow, book_id, current_user)
        cid = await uow.collab.add_comment(
            book_id=book_id,
            chapter_ep=chapter_ep,
            author_name=req.author_name or current_user.display_name or "Anonymous",
            content=req.content,
            anchor_text=req.anchor_text,
            parent_id=req.parent_id,
        )
    return {"status": "success", "id": cid}


@router.get("/books/{book_id}/comments")
async def list_comments(
    book_id: int,
    chapter_ep: int | None = Query(None),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with UnitOfWork(AppContainer.db()) as uow:
        await _verify_book_access(uow, book_id, current_user)
        comments = await uow.collab.list_comments(book_id, chapter_ep)
    return [
        {
            "id": c.id,
            "chapter_ep": c.chapter_ep,
            "anchor_text": c.anchor_text,
            "author_name": c.author_name,
            "content": c.content,
            "resolved": c.resolved,
            "parent_id": c.parent_id,
            "created_at": str(c.created_at),
        }
        for c in comments
    ]


@router.patch("/comments/{comment_id}/resolve")
async def resolve_comment(
    comment_id: int,
    payload: dict[str, Any] = {},
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """コメントを解決済みにする。

    所有権検証が必須。`comment_id` はグローバル採番で、呼び出し側から
    どの作品のコメントかは判断できないため、まず `comment.book_id` を
    解決して `_verify_book_access` を通す。これが無いと
    任意の認証ユーザーが他人のレビューコメントを握り潰せた。
    """
    resolved = bool(payload.get("resolved", True))
    async with UnitOfWork(AppContainer.db()) as uow:
        comment = await uow.collab.get_comment(comment_id)
        if not comment:
            from src.core.exceptions import NotFoundError

            raise NotFoundError(
                "Comment not found", resource_type="Comment", resource_id=str(comment_id)
            )
        book_id = int(comment.book_id)
        await _verify_book_access(uow, book_id, current_user)
        # book_id を渡して DB 層でも絞る（呼び出し側の検証漏れに対する多層防御）
        n = await uow.collab.resolve_comment(comment_id, resolved, book_id=book_id)
    if n == 0:
        from src.core.exceptions import NotFoundError

        raise NotFoundError(
            "Comment not found", resource_type="Comment", resource_id=str(comment_id)
        )
    return {"status": "success", "id": comment_id, "resolved": resolved}


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """コメントを削除する。所有権検証は必須（`resolve_comment` 参照）。"""
    async with UnitOfWork(AppContainer.db()) as uow:
        comment = await uow.collab.get_comment(comment_id)
        if not comment:
            from src.core.exceptions import NotFoundError

            raise NotFoundError(
                "Comment not found", resource_type="Comment", resource_id=str(comment_id)
            )
        book_id = int(comment.book_id)
        await _verify_book_access(uow, book_id, current_user)
        n = await uow.collab.delete_comment(comment_id, book_id=book_id)
    if n == 0:
        from src.core.exceptions import NotFoundError

        raise NotFoundError(
            "Comment not found", resource_type="Comment", resource_id=str(comment_id)
        )
    return {"status": "success", "id": comment_id}
