"""
database/repositories/collab.py - 共同執筆・レビューコメント用リポジトリ
"""

from __future__ import annotations

from sqlalchemy import select

from src.backend.database.models import Comment, ProjectMember
from src.services.errors import retry_on_lock


class CollabRepository:
    def __init__(self, session):
        self.session = session

    # ---- Members ----
    @retry_on_lock()
    async def add_member(self, book_id: int, user_name: str, role: str = "viewer") -> int:
        member = ProjectMember(book_id=book_id, user_name=user_name, role=role)
        self.session.add(member)
        await self.session.flush()
        return member.id

    @retry_on_lock()
    async def list_members(self, book_id: int) -> list[ProjectMember]:
        result = await self.session.execute(
            select(ProjectMember).where(ProjectMember.book_id == book_id).order_by(ProjectMember.id)
        )
        return list(result.scalars().all())

    @retry_on_lock()
    async def remove_member(self, member_id: int) -> int:
        from sqlalchemy import delete

        result = await self.session.execute(
            delete(ProjectMember).where(ProjectMember.id == member_id)
        )
        return result.rowcount

    # ---- Comments ----
    @retry_on_lock()
    async def add_comment(
        self,
        book_id: int,
        chapter_ep: int,
        author_name: str,
        content: str,
        anchor_text: str = "",
        parent_id: int | None = None,
    ) -> int:
        comment = Comment(
            book_id=book_id,
            chapter_ep=chapter_ep,
            anchor_text=anchor_text,
            author_name=author_name,
            content=content,
            parent_id=parent_id,
            resolved=False,
        )
        self.session.add(comment)
        await self.session.flush()
        return comment.id

    @retry_on_lock()
    async def list_comments(self, book_id: int, chapter_ep: int | None = None) -> list[Comment]:
        stmt = select(Comment).where(Comment.book_id == book_id)
        if chapter_ep is not None:
            stmt = stmt.where(Comment.chapter_ep == chapter_ep)
        stmt = stmt.order_by(Comment.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    @retry_on_lock()
    async def get_comment(self, comment_id: int) -> "Comment | None":
        """コメント ID からコメントを取得する（所有権検証の前提）。

        `comment_id` はグローバル採番であり、呼び出し側からは
        どの作品のコメントか判断できない。所有権検証のためには
        まず `comment.book_id` を取り出す必要があるため、本メソッドを
        経由しない所有者検証は実施できない。
        """
        result = await self.session.execute(
            select(Comment).where(Comment.id == comment_id)
        )
        return result.scalar_one_or_none()

    @retry_on_lock()
    async def resolve_comment(
        self, comment_id: int, resolved: bool = True, book_id: int | None = None
    ) -> int:
        """コメントを解決済みにする。`book_id` を渡すと作品で絞り込む。

        `book_id` による絞りは呼び出し側が所有権検証を忘れた場合の
        多層防御。IDOR を DB 層でも落とす。
        """
        from sqlalchemy import update

        stmt = update(Comment).where(Comment.id == comment_id)
        if book_id is not None:
            stmt = stmt.where(Comment.book_id == book_id)
        result = await self.session.execute(stmt.values(resolved=resolved))
        return result.rowcount

    @retry_on_lock()
    async def delete_comment(self, comment_id: int, book_id: int | None = None) -> int:
        """コメントを削除する。`book_id` を渡すと作品で絞り込む。

        `book_id` による絞りは呼び出し側が所有権検証を忘れた場合の
        多層防御。IDOR を DB 層でも落とす。
        """
        from sqlalchemy import delete

        stmt = delete(Comment).where(Comment.id == comment_id)
        if book_id is not None:
            stmt = stmt.where(Comment.book_id == book_id)
        result = await self.session.execute(stmt)
        return result.rowcount
