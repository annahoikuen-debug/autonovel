"""Book (ORM) と Novel (Domain Entity) の双方向マッパー。"""

from __future__ import annotations

from src.infrastructure.database.models.book import Book
from src.domain.entities.novel import Novel
from src.domain.value_objects.ids import NovelId, UserId
from src.domain.value_objects.metadata import NovelMode, NovelStatus
from src.domain.value_objects.text import Catchcopy, Genre, Summary, Title


class BookMapper:
    """SQLAlchemy ORM Book (int主キー) と Domain Entity Novel の双方向変換マッパー。"""

    @staticmethod
    def to_domain(orm: Book) -> Novel:
        """ORM Book -> Domain Novel"""
        # int id を str 経由で NovelId にマッピング
        novel_id = NovelId(value=str(orm.id))  # type: ignore[arg-type]
        author_id = UserId(value=str(orm.user_id))  # type: ignore[arg-type]

        status = NovelStatus.DRAFT
        if hasattr(orm, "status") and orm.status:
            try:
                status = NovelStatus(orm.status.lower())
            except ValueError:
                status = NovelStatus.DRAFT

        mode = NovelMode.EASY
        if hasattr(orm, "mode") and orm.mode:
            try:
                mode = NovelMode(orm.mode.lower())
            except ValueError:
                mode = NovelMode.EASY

        return Novel(
            id=novel_id,
            title=Title(orm.title or ""),  # type: ignore[arg-type]
            author_id=author_id,
            genre=Genre(orm.genre or ""),  # type: ignore[arg-type]
            catchcopy=Catchcopy(getattr(orm, "catchcopy", "") or ""),  # type: ignore[arg-type]
            synopsis=Summary(orm.synopsis or ""),  # type: ignore[arg-type]
            concept=Summary(orm.concept or ""),  # type: ignore[arg-type]
            status=status,
            mode=mode,
            target_episodes=getattr(orm, "target_eps", 50) or 50,
            style_dna=getattr(orm, "style_dna", getattr(orm, "style_key", "")) or "",
            created_at=orm.created_at,  # type: ignore[arg-type]
            updated_at=getattr(orm, "updated_at", orm.created_at) or orm.created_at,  # type: ignore[arg-type]
            cumulative_tension=int(getattr(orm, "cumulative_tension", 0.0) or 0),
        )

    @staticmethod
    def to_orm(entity: Novel, existing_orm: Book | None = None) -> Book:
        """Domain Novel -> ORM Book"""
        orm = existing_orm or Book()

        # IDがint変換可能な場合は設定
        if hasattr(entity.id, "value") and entity.id.value.isdigit():  # type: ignore[attr-defined]
            orm.id = int(entity.id.value)  # type: ignore[assignment]

        if hasattr(entity.author_id, "value") and entity.author_id.value.isdigit():  # type: ignore[attr-defined]
            orm.user_id = int(entity.author_id.value)  # type: ignore[assignment]

        orm.title = entity.title.value if hasattr(entity.title, "value") else str(entity.title)  # type: ignore[assignment]
        orm.genre = entity.genre.value if hasattr(entity.genre, "value") else str(entity.genre)  # type: ignore[assignment]
        orm.concept = entity.concept.value if hasattr(entity.concept, "value") else str(entity.concept)  # type: ignore[assignment]
        orm.synopsis = entity.synopsis.value if hasattr(entity.synopsis, "value") else str(entity.synopsis)  # type: ignore[assignment]
        orm.catchcopy = entity.catchcopy.value if hasattr(entity.catchcopy, "value") else str(entity.catchcopy)  # type: ignore[assignment]
        orm.target_eps = entity.target_episodes  # type: ignore[assignment]
        orm.style_key = entity.style_dna  # type: ignore[attr-defined]
        orm.status = entity.status.value if hasattr(entity.status, "value") else str(entity.status)  # type: ignore[assignment]
        orm.cumulative_tension = float(entity.cumulative_tension)  # type: ignore[assignment]
        return orm
