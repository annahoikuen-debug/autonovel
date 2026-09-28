from __future__ import annotations

"""
database/repo_book.py - 作品(Books)データ操作用のリポジトリMixin
"""
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select, update

from src.backend.database.models import Book, Chapter, Plot
from src.services.errors import retry_on_lock

if TYPE_CHECKING:
    from src.models import BookDbModel

logger = logging.getLogger(__name__)

from src.backend.database.repositories.base import BaseRepository


class BookRepository(BaseRepository):
    """Booksテーブルに関するDB操作をまとめたMixin

    v5.3 / C0 修正: 執筆エージェント（`WritingAgent` / `EpisodeWriter`）は
    作品単位ではなく1話完結の単位（章）を操作する。当該エージェントには
    本リポジトリ 1 つが注入される（`src/backend/tasks/generation_tasks.py:151`）
    ため、章操作と聖書読み出しを本リポジトリからも提供しないと
    `AttributeError` で本番執筆が失敗する。
    実体は `ChapterRepository` / `BibleRepository` に委譲し、
    呼び出し側の契約（`WritingAgent(repo=...)`）は変更しない。
    """


    @retry_on_lock()
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
        book = Book(
            user_id=user_id,
            title=title,
            genre=genre,
            concept=concept,
            synopsis=synopsis,
            target_eps=target_eps,
            style_dna=json.dumps(style_dna, ensure_ascii=False),
            marketing_data=json.dumps(marketing_data, ensure_ascii=False),
            created_at=datetime.now(),
        )
        self.session.add(book)
        await self.session.flush()
        return book.id

    async def get_book(self, book_id: int, user_id: int | None = None) -> BookDbModel | None:
        stmt = select(Book).where(Book.id == book_id)
        if user_id is not None:
            stmt = stmt.where(Book.user_id == user_id)
        result = await self.session.execute(stmt)
        book = result.scalar_one_or_none()
        if not book:
            return None
        d = self._to_dict(book)
        d = self._parse_row(d, ["style_dna", "marketing_data"])
        from src.models import BookDbModel

        return BookDbModel(**d)

    async def get_all_books(self, user_id: int | None = None) -> list[BookDbModel]:
        stmt = select(Book).order_by(Book.id.desc())
        if user_id is not None:
            stmt = stmt.where(Book.user_id == user_id)
        result = await self.session.execute(stmt)
        books = result.scalars().all()
        from src.models import BookDbModel

        return [
            BookDbModel(**self._parse_row(self._to_dict(b), ["style_dna", "marketing_data"]))
            for b in books
        ]

    @retry_on_lock()
    async def update_book_cumulative_tension(self, book_id: int, user_id: int, tension: int) -> None:
        await self.session.execute(
            update(Book).where(Book.id == book_id, Book.user_id == user_id).values(cumulative_tension=tension)
        )

    @retry_on_lock()
    async def update_book_cumulative_stress(self, book_id: int, user_id: int, stress: int) -> None:
        # stress is mapped to cumulative_tension
        await self.session.execute(
            update(Book).where(Book.id == book_id, Book.user_id == user_id).values(cumulative_tension=stress)
        )

    @retry_on_lock()
    async def delete_book(self, book_id: int, user_id: int) -> None:
        await self.session.execute(delete(Book).where(Book.id == book_id, Book.user_id == user_id))

    @retry_on_lock()
    async def update_book_marketing_data(
        self, book_id: int, user_id: int, title: str, marketing_data: dict[str, Any]
    ) -> None:
        """作品名とマーケティングデータを更新する。既存のデータがある場合はマージを試みる。"""
        import traceback

        result = await self.session.execute(select(Book.marketing_data).where(Book.id == book_id, Book.user_id == user_id))
        row_val = result.scalar_one_or_none()
        current_data = {}
        if row_val:
            try:
                current_data = json.loads(row_val) if isinstance(row_val, str) else row_val
            except Exception as e:
                logger.warning(
                    f"Failed to parse marketing_data JSON: {e}\n{traceback.format_exc()}"
                )

        merged = {**current_data, **marketing_data}
        await self.session.execute(
            update(Book)
            .where(Book.id == book_id, Book.user_id == user_id)
            .values(title=title, marketing_data=json.dumps(merged, ensure_ascii=False))
        )

    @retry_on_lock()
    async def update_book_target_eps(self, book_id: int, user_id: int, new_total_eps: int) -> None:
        """作品の目標話数を更新する"""
        await self.session.execute(
            update(Book).where(Book.id == book_id, Book.user_id == user_id).values(target_eps=new_total_eps)
        )

    @retry_on_lock()
    async def recalculate_book_tension(self, book_id: int, user_id: int, branch_id: int = 1) -> int:
        """指定ブランチの全チャプターの tension_delta を合計して累積テンションを再計算し、DBを更新する"""
        result = await self.session.execute(
            select(Chapter.tension_delta).where(Chapter.book_id == book_id, Chapter.user_id == user_id, Chapter.branch_id == branch_id)
        )
        rows = result.scalars().all()
        total_tension = sum(t or 0 for t in rows)
        await self.session.execute(
            update(Book).where(Book.id == book_id, Book.user_id == user_id).values(cumulative_tension=total_tension)
        )
        return total_tension

    @retry_on_lock()
    async def recalculate_book_comfort(self, book_id: int, user_id: int, branch_id: int = 1) -> tuple[int, int]:
        """指定ブランチの全チャプターの qol_delta を合計して累積QOLを再計算し、DBを更新する"""
        result = await self.session.execute(
            select(Chapter.qol_delta).where(Chapter.book_id == book_id, Chapter.user_id == user_id, Chapter.branch_id == branch_id)
        )
        rows = result.scalars().all()
        total_qol = sum(q or 0 for q in rows)

        plot_result = await self.session.execute(
            select(Plot.state_integrity_score)
            .where(Plot.book_id == book_id, Plot.branch_id == branch_id)
            .order_by(Plot.ep_num.desc())
            .limit(1)
        )
        latest_plot_score = plot_result.scalar_one_or_none()
        integrity = latest_plot_score if latest_plot_score is not None else 100

        await self.session.execute(
            update(Book)
            .where(Book.id == book_id, Book.user_id == user_id)
            .values(cumulative_qol=total_qol, sanctuary_integrity=integrity)
        )
        return total_qol, integrity

    @retry_on_lock()
    async def recalculate_book_cost(self, book_id: int, user_id: int, branch_id: int = 1) -> float:
        """最新のプロットから代償蓄積スコアを取得し、DBを更新する"""
        plot_result = await self.session.execute(
            select(Plot.cost_score)
            .where(Plot.book_id == book_id, Plot.branch_id == branch_id)
            .where(Plot.status == "expanded")
            .order_by(Plot.ep_num.desc())
            .limit(1)
        )
        latest_plot_cost = plot_result.scalar_one_or_none()
        total_cost = latest_plot_cost if latest_plot_cost is not None else 0.0

        await self.session.execute(
            update(Book).where(Book.id == book_id, Book.user_id == user_id).values(cumulative_cost=total_cost)
        )
        return total_cost

    # ── v5.3 / C0: 執筆エージェント用の章操作（委譲） ─────────────
    # 執筆エージェント（WritingAgent / EpisodeWriter）は 1話完結の単位（章）を
    # 操作するが、注入されるのは本リポジトリ 1 つだけである
    # （generation_tasks.py:151）。ここで ChapterRepository へ委譲し、
    # 呼び出し側の契約を変更せずに AttributeError を解消する。

    def _chapter_repo(self) -> Any:
        """章操作の実体を返す。

        `ChapterRepository` の import はメソッド内で遅延実行する。
        モジュール直下の import だと
        `src.backend.database.repository` → `repositories.book` → 本ファイル
        の循環インポートになるため。
        """
        from src.infrastructure.repositories.chapter import ChapterRepository

        return ChapterRepository(self.session)

    def _bible_repo(self) -> Any:
        from src.infrastructure.repositories.bible import BibleRepository

        return BibleRepository(self.session)

    async def save_chapter(
        self,
        book_id: int,
        branch_id: int,
        ep_num: int,
        title: str,
        content: str,
        summary: str = "",
        killer_phrase: str | None = None,
        ai_insight: str = "",
        tension_delta: int = 0,
        qol_delta: int = 0,
    ) -> None:
        """1話分の本文を保存する（既存があれば更新）。

        `ChapterRepository.create_chapter` は upsert 仕様のため、
        委譲後に「重複行が増えない」ことが保証される。

        Args:
            book_id: 作品ID
            branch_id: ブランチID
            ep_num: 话数（1-indexed）
            title: 話タイトル
            content: 本文
            summary: 概要（未設定なら本文冒頭から自動生成）
            killer_phrase: 名台詞
            ai_insight: AI所感
            tension_delta: テンション変動
            qol_delta: QOL変動
        """
        await self._chapter_repo().create_chapter(
            book_id=book_id,
            ep_num=ep_num,
            title=title,
            content=content,
            summary=summary or (content[:200] if content else ""),
            killer_phrase=killer_phrase,
            ai_insight=ai_insight,
            world_state={},
            trinity_review_log={},
            created_at=datetime.now(timezone.utc).isoformat(),
            tension_delta=tension_delta,
            qol_delta=qol_delta,
            branch_id=branch_id,
        )

    async def get_chapter(self, branch_id: int, ep_num: int) -> Any:
        """指定話数の章を取得する（無ければ None）。"""
        return await self._chapter_repo().get_chapter(branch_id=branch_id, ep_num=ep_num)

    async def update_chapter_content(self, branch_id: int, ep_num: int, content: str) -> None:
        """指定話数の本文を差し替える（再生成・局所パッチ適用で使用）。"""
        await self._chapter_repo().update_chapter_content(
            branch_id=branch_id, ep_num=ep_num, content=content
        )

    async def get_latest_bible(self, book_id: int) -> Any:
        """最新の聖書（world bible）を取得する（無ければ None）。"""
        return await self._bible_repo().get_latest_bible(book_id)
