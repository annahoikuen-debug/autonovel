from __future__ import annotations

"""
database/repo_chapter.py - チャプター(Chapters)本文データ操作用のリポジトリMixin
"""
import json
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, or_, select, update

from src.backend.database.models import Chapter
from src.services.errors import retry_on_lock

if TYPE_CHECKING:
    from src.models import ChapterDbModel


from src.backend.database.repositories.base import BaseRepository


class _Unset:
    """「この引数は渡されていない」を表す番兵。

    生成済みメタデータ（``killer_phrase`` / ``ai_insight`` / ``world_state`` /
    ``trinity_review_log``）を、部分更新のときに消さないようにするために使う。
    既定値を ``""`` や ``{}`` にすると、upsert のたびに生成済み値が
    上書きされて消えていた。
    """

    _instance: _Unset | None = None

    def __new__(cls) -> _Unset:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET = _Unset()


def _as_datetime(value: Any) -> datetime | None:
    """``created_at`` を ``CompatibleDateTime`` が受け付ける datetime に正規化する。

    ``CompatibleDateTime.process_bind_param`` は ``value.tzinfo`` を前提とするため、
    ISO 文字列を代入すると StatementError になる。呼び出し側が
    ``datetime.now(timezone.utc).isoformat()`` を渡して flush で落ちるのを防ぐ。
    """
    if value is None or value is UNSET:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise TypeError(f"created_at に解釈できない型が渡されました: {type(value)!r}")


def _as_json_text(value: Any) -> str:
    """dict / list は JSON 文字列に、それ以外はそのまま文字列化する。"""
    if isinstance(value, str):
        return value or "{}"
    if value is None:
        return "{}"
    return json.dumps(value, ensure_ascii=False)


class ChapterRepository(BaseRepository):
    """Chaptersテーブルに関するDB操作をまとめたMixin"""

    @retry_on_lock()
    async def create_chapter(
        self,
        book_id: int,
        ep_num: int,
        title: str,
        content: str,
        summary: str,
        killer_phrase: Any = UNSET,
        ai_insight: Any = UNSET,
        world_state: Any = UNSET,
        trinity_review_log: Any = UNSET,
        created_at: Any = UNSET,
        tension_delta: Any = UNSET,
        qol_delta: Any = UNSET,
        branch_id: int = 1,
    ) -> bool:
        """1 話を Upsert する。既存行があれば更新、無ければ作成する。

        ``chapters`` の一意制約は ``UNIQUE(book_id, branch_id, ep_num)``。
        ``branch_id`` は作品ごとには固有ではなく既定値 1 が全作品で使われるため、
        照合には必ず ``book_id`` も含めること（``book_id`` を落とすと他作品の行を
        巻き込んで上書きする，或者 ``MultipleResultsFound`` で落ちる）。

        ``killer_phrase`` などの生成済みメタデータは「渡されていない」限り一切
        触らないため、既存値を壊さない。``UNSET`` と ``None`` のどちらも
        「渡されていない」として扱う（明示的に空にしたい場合は ``""`` を渡す）。
        ``None`` を未指定扱いにしてあるのは、``None``/``""``/``"{}"`` を
        そのまま渡す旧呼び出し側（例: ``BookRepository.save_chapter``）が
        保存のたびに生成済み値を消していたのを、呼び出し側が壊なくても
        直る必要があるため。

        Returns:
            既存行を更新したなら True、新規作成なら False。
        """
        result = await self.session.execute(
            select(Chapter)
            .where(Chapter.book_id == book_id)
            .where(Chapter.branch_id == branch_id)
            .where(Chapter.ep_num == ep_num)
        )
        ch = result.scalar_one_or_none()
        created = ch is None
        if created:
            ch = Chapter(
                book_id=book_id,
                branch_id=branch_id,
                ep_num=ep_num,
                killer_phrase=None,
                ai_insight="",
                world_state="{}",
                trinity_review_log="{}",
            )
            self.session.add(ch)

        ch.title = title
        ch.content = content
        ch.summary = (
            summary if isinstance(summary, str) else json.dumps(summary, ensure_ascii=False)
        )
        if killer_phrase is not UNSET and killer_phrase is not None:
            ch.killer_phrase = killer_phrase
        if ai_insight is not UNSET and ai_insight is not None:
            ch.ai_insight = ai_insight
        if world_state is not UNSET and world_state is not None:
            ch.world_state = _as_json_text(world_state)
        if trinity_review_log is not UNSET and trinity_review_log is not None:
            ch.trinity_review_log = _as_json_text(trinity_review_log)
        created_dt = _as_datetime(created_at)
        if created_dt is not None:
            ch.created_at = created_dt
        if tension_delta is not UNSET:
            ch.tension_delta = tension_delta
        if qol_delta is not UNSET:
            ch.qol_delta = qol_delta
        return not created

    async def get_chapter(
        self, branch_id: int, ep_num: int, book_id: int | None = None
    ) -> ChapterDbModel | None:
        """1 話を取得する。

        ``branch_id`` は作品間で共有される（既定値 1）ため、``book_id`` を
        渡さないと同じ branch_id の**他作品**の行を掴んでしまう
        （``create_chapter`` の docstring と同じ理由）。省略は後方互換のため
        許容するが、呼び出し側は必ず ``book_id`` を渡すこと。
        """
        stmt = select(Chapter).where(Chapter.branch_id == branch_id).where(Chapter.ep_num == ep_num)
        if book_id is not None:
            stmt = stmt.where(Chapter.book_id == book_id)
        result = await self.session.execute(stmt)
        ch = result.scalar_one_or_none()
        if not ch:
            return None
        from src.models import ChapterDbModel

        return ChapterDbModel(
            **self._parse_row(self._to_dict(ch), ["world_state", "trinity_review_log", "summary"])
        )

    async def get_chapters_before(
        self, branch_id: int, ep_num: int, book_id: int | None = None
    ) -> list[ChapterDbModel]:
        stmt = (
            select(Chapter)
            .where(Chapter.branch_id == branch_id)
            .where(Chapter.ep_num < ep_num)
        )
        if book_id is not None:
            stmt = stmt.where(Chapter.book_id == book_id)
        result = await self.session.execute(stmt.order_by(Chapter.ep_num.desc()))
        chaps = result.scalars().all()
        from src.models import ChapterDbModel

        return [
            ChapterDbModel(
                **self._parse_row(
                    self._to_dict(c), ["world_state", "trinity_review_log", "summary"]
                )
            )
            for c in chaps
        ]

    async def get_all_non_anchor_chapters(
        self,
        book_id: int,
        branch_id: int | None = None,
        order_by: str = "ep_num",
        limit: int | None = None,
    ) -> list[ChapterDbModel]:
        """指定作品のアンカーではない章をすべて取得する。

        第1引数は **book_id** である（``src/core/interfaces.py`` の
        ``get_all_non_anchor_chapters(self, book_id, ...)`` と同じ契約）。
        ``branch_id`` 省略時は既定ブランチ 1 を使う。

        ここを ``WHERE branch_id = book_id`` で絞り込むと、branch_id 1 を共有する
        他作品の本編が混ざるため、必ず ``book_id`` も条件にすること。
        """
        target_branch_id = branch_id if branch_id is not None else 1
        stmt = (
            select(Chapter)
            .where(Chapter.book_id == book_id)
            .where(Chapter.branch_id == target_branch_id)
            .where(Chapter.is_anchor.is_(False))
        )
        if "desc" in order_by.lower():
            stmt = stmt.order_by(Chapter.ep_num.desc())
        else:
            stmt = stmt.order_by(Chapter.ep_num)
        if limit:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        chaps = result.scalars().all()
        from src.models import ChapterDbModel

        return [
            ChapterDbModel(
                **self._parse_row(
                    self._to_dict(c), ["world_state", "trinity_review_log", "summary"]
                )
            )
            for c in chaps
        ]

    @retry_on_lock()
    async def delete_chapter(
        self, book_id: int, ep_num: int, branch_id: int | None = None
    ) -> int:
        """指定作品の 1 話を削除する。

        ``book_id`` を条件に含めるのは ``delete_chapter`` が所有者的検証済みの
        book_id で呼ばれるためで、付けないと他作品の同番の章が消える。

        Returns:
            削除した行数（0 なら対象なし）。
        """
        target_branch_id = branch_id if branch_id is not None else 1
        result = await self.session.execute(
            delete(Chapter)
            .where(Chapter.book_id == book_id)
            .where(Chapter.branch_id == target_branch_id)
            .where(Chapter.ep_num == ep_num)
        )
        return int(result.rowcount or 0)

    @retry_on_lock()
    async def update_chapter_content(
        self, branch_id: int, ep_num: int, content: str, book_id: int | None = None
    ) -> int:
        """1 話の本文を差し替える。

        ``branch_id`` は作品間で共有される（既定 1）ため、HTTP 経由の書き込みでは
        ``book_id`` を必ず渡して他作品へ及ばないようにする。
        """
        stmt = (
            update(Chapter)
            .where(Chapter.branch_id == branch_id)
            .where(Chapter.ep_num == ep_num)
        )
        if book_id is not None:
            stmt = stmt.where(Chapter.book_id == book_id)
        result = await self.session.execute(stmt.values(content=content))
        return int(result.rowcount or 0)

    @retry_on_lock()
    async def update_chapter_candidates(
        self, branch_id: int, ep_num: int, candidates: list[Any], book_id: int | None = None
    ) -> int:
        """チャプターの候補案のみを更新する"""
        stmt = (
            update(Chapter)
            .where(Chapter.branch_id == branch_id)
            .where(Chapter.ep_num == ep_num)
        )
        if book_id is not None:
            stmt = stmt.where(Chapter.book_id == book_id)
        result = await self.session.execute(
            stmt.values(candidates=json.dumps(candidates, ensure_ascii=False))
        )
        return int(result.rowcount or 0)

    async def get_relevant_past_logs(
        self,
        branch_id: int,
        current_ep: int,
        query_text: str = "",
        top_k: int = 5,
        book_id: int | None = None,
    ) -> str:
        """【強化版RAG機能】現在のプロットに含まれるキーワードに基づき、過去の重要ログを抽出する。"""
        if not query_text:
            return ""
        keywords = re.findall(r"[一-龠々]{2,}|[ァ-ヶー]{2,}", query_text)
        if not keywords:
            return ""
        stmt = (
            select(Chapter).where(Chapter.branch_id == branch_id).where(Chapter.ep_num < current_ep)
        )
        if book_id is not None:
            stmt = stmt.where(Chapter.book_id == book_id)
        like_clauses = [Chapter.content.like(f"%{k}%") for k in keywords[:5]]
        stmt = stmt.where(or_(*like_clauses))
        stmt = stmt.order_by(Chapter.ep_num.desc()).limit(top_k)
        result = await self.session.execute(stmt)
        chaps = result.scalars().all()

        if not chaps:
            return ""

        res = "【過去の関連文脈（RAG）】\n"
        for c in chaps:
            res += f"- 第{c.ep_num}話: {c.summary} (重要事項: {c.ai_insight})\n"
        return res
