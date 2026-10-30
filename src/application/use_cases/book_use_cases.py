"""Book (作品) に関するアプリケーションユースケース群。"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from src.application.ports.book_repository import IBookRepository
from src.application.ports.unit_of_work import IUnitOfWork
from src.core.exceptions import NotFoundError


@dataclass
class BookDTO:
    id: int
    title: str
    genre: str
    concept: str
    synopsis: str
    target_eps: int
    cumulative_stress: float
    created_at: Any

    @classmethod
    def from_orm(cls, b: Any) -> BookDTO:
        return cls(
            id=b.id,
            title=b.title,
            genre=b.genre or "",
            concept=b.concept or "",
            synopsis=b.synopsis or "",
            target_eps=b.target_eps or 10,
            cumulative_stress=b.cumulative_tension or 0.0,
            created_at=b.created_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "genre": self.genre,
            "concept": self.concept,
            "synopsis": self.synopsis,
            "target_eps": self.target_eps,
            "cumulative_stress": self.cumulative_stress,
            "created_at": self.created_at,
        }


class BookUseCases:
    """書籍関連のオーケストレーションを行うユースケース集約。"""

    def __init__(
        self,
        uow: IUnitOfWork | None = None,
        book_repository: IBookRepository | None = None,
    ):
        self._uow = uow
        self.book_repository = book_repository

    async def _get_uow(self) -> IUnitOfWork:
        if self._uow is not None:
            return self._uow
        raise RuntimeError(
            "uow が未設定です。BookUseCases に uow を渡してください。"
        )

    async def list_books(self, user_id: int) -> list[dict[str, Any]]:
        """ユーザーの作品一覧を取得"""
        uow = self._get_uow()
        _ = uow  # トランザクションコンテキスト確保のため取得
        books = await self.book_repository.get_all_books(user_id=user_id)
        return [BookDTO.from_orm(b).to_dict() for b in books]

    async def get_book(self, book_id: int, current_user: Any) -> dict[str, Any]:
        """指定されたIDの作品を取得（所有権または管理者権限を検証）"""
        uow = self._get_uow()
        _ = uow
        b = await self.book_repository.get_book(book_id=book_id, user_id=current_user.id)
        if not b:
            other_book = await self.book_repository.get_book_by_id(book_id)
            if other_book and other_book.user_id != current_user.id and current_user.role != "admin":
                from fastapi import HTTPException, status
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="この作品に対するアクセス権限がありません")
            raise NotFoundError("Book not found", resource_type="Book", resource_id=str(book_id))

        return BookDTO.from_orm(b).to_dict()

    async def create_book(self, payload: Any, current_user: Any) -> dict[str, Any]:
        """新規作品を作成"""
        uow = self._get_uow()
        _ = uow
        book_id = await self.book_repository.create_book(
            user_id=current_user.id,
            title=payload.title,
            genre=payload.genre or "ファンタジー",
            concept=payload.concept or "",
            synopsis=payload.synopsis or "",
            target_eps=payload.target_eps or 10,
            style_dna={},
            marketing_data={},
        )
        b = await self.book_repository.get_book(book_id=book_id, user_id=current_user.id)
        if not b:
            raise NotFoundError("Book not found after creation", resource_type="Book", resource_id=str(book_id))

        return BookDTO.from_orm(b).to_dict()

    async def delete_book(self, book_id: int, current_user: Any) -> None:
        """作品を削除"""
        uow = self._get_uow()
        _ = uow
        b = await self.book_repository.get_book(book_id=book_id, user_id=current_user.id)
        if not b:
            other_book = await self.book_repository.get_book_by_id(book_id)
            if other_book and other_book.user_id != current_user.id and current_user.role != "admin":
                from fastapi import HTTPException, status
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="この作品に対するアクセス権限がありません")
            raise NotFoundError("Book not found", resource_type="Book", resource_id=str(book_id))

        await self.book_repository.delete_book(book_id=book_id, user_id=current_user.id)

    async def get_book_score_history(self, book_id: int) -> dict[str, Any]:
        """スコア履歴を取得"""
        uow = self._get_uow()
        book = await self.book_repository.get_book(book_id)
        if not book:
            raise NotFoundError("Book not found", resource_type="Book", resource_id=str(book_id))

        history = await uow.book_scores.get_history_for_book(book_id)
        all_benchmarks = await uow.book_scores.get_genre_benchmarks()
        genre_benchmark = all_benchmarks.get(book.genre) if all_benchmarks else None

        return {
            "success": True,
            "book_id": book_id,
            "history": [
                {
                    "chapter_number": h.chapter_number,
                    "overall_score": h.overall_score,
                    "structure_score": h.structure_score,
                    "coherency_score": h.coherency_score,
                    "factual_grounding_score": h.factual_grounding_score,
                    "visual_textual_synergy_score": h.visual_textual_synergy_score,
                    "reader_experience_score": h.reader_experience_score,
                    "evaluated_at": h.evaluated_at,
                    "evaluator_version": h.evaluator_version,
                }
                for h in history
            ],
            "benchmarks": genre_benchmark,
        }

    async def get_pdca_cycles(self, book_id: int, chapter_number: int) -> list[dict[str, Any]]:
        """PDCA履歴を取得"""
        uow = self._get_uow()
        snapshots = await uow.pdca_history.get_by_chapter(book_id, chapter_number)

        return [
            {
                "book_id": s.book_id,
                "chapter_number": s.chapter_number,
                "cycle_number": s.cycle_number,
                "initial_score": s.initial_score,
                "final_score": s.final_score,
                "score_delta": s.score_delta,
                "improved_percentage": s.improved_percentage,
                "lowest_dimension": s.lowest_dimension,
                "directives": s.directives,
                "history": s.history,
                "converged": s.converged,
                "created_at": s.created_at,
            }
            for s in snapshots
        ]
