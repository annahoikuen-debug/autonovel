from __future__ import annotations

"""
database/repo_bible.py - バイブル(Bible)データ操作用のリポジトリMixin
"""
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from src.backend.database.models import Bible, BiblePendingSetting, Book, Branch, Character, Plot

if TYPE_CHECKING:
    from src.models import BibleDbModel, WorldBible

logger = logging.getLogger(__name__)


from src.backend.database.repositories.base import BaseRepository


class BibleRepository(BaseRepository):
    """Bibleテーブルに関するDB操作をまとめたMixin"""

    async def create_bible(
        self, book_id: int, settings: Any, version: int, last_updated: str
    ) -> None:
        bible = Bible(
            book_id=book_id,
            settings=json.dumps(settings, ensure_ascii=False)
            if not isinstance(settings, str)
            else settings,
            version=version,
            last_updated=last_updated,
        )
        self.session.add(bible)

    async def get_latest_bible(self, book_id: int) -> BibleDbModel | None:
        result = await self.session.execute(
            select(Bible).where(Bible.book_id == book_id).order_by(Bible.id.desc()).limit(1)
        )
        bible = result.scalar_one_or_none()
        if not bible:
            return None
        from src.models import BibleDbModel

        return BibleDbModel(**self._parse_row(self._to_dict(bible), ["settings"]))

    async def save_full_world_bible(self, bible: WorldBible, **kwargs) -> int:
        """WorldBible オブジェクトとその構成要素を一括保存する。book_id が指定されている場合は更新を行う。"""
        import traceback

        book_id = kwargs.get("book_id")
        branch_id = 1
        try:
            style_dna = json.dumps({"mode": bible.style_key}, ensure_ascii=False)
            mkt_data = json.dumps(bible.marketing_assets.model_dump(), ensure_ascii=False)

            if book_id:
                result = await self.session.execute(select(Book).where(Book.id == book_id))
                book_obj = result.scalar_one_or_none()
                if not book_obj:
                    raise ValueError(f"Book with ID {book_id} not found.")

                current_mkt = {}
                if book_obj.marketing_data:
                    try:
                        current_mkt = json.loads(book_obj.marketing_data)
                    except (json.JSONDecodeError, ValueError):
                        pass

                new_mkt = bible.marketing_assets.model_dump()
                merged_mkt = {
                    "catchcopies": current_mkt.get("catchcopies")
                    if current_mkt.get("catchcopies")
                    else new_mkt.get("catchcopies"),
                    "tags": current_mkt.get("tags")
                    if current_mkt.get("tags")
                    else new_mkt.get("tags"),
                    "ab_test_candidates": new_mkt.get("ab_test_candidates"),
                }
                mkt_data = json.dumps(merged_mkt, ensure_ascii=False)

                branch_id = book_obj.current_branch_id

                book_obj.title = bible.title
                book_obj.genre = bible.genre
                book_obj.concept = bible.concept
                book_obj.synopsis = bible.synopsis
                book_obj.target_eps = kwargs.get("target_eps", 50)
                book_obj.style_dna = style_dna
                book_obj.marketing_data = mkt_data
            else:
                book_obj = Book(
                    title=bible.title,
                    genre=bible.genre,
                    concept=bible.concept,
                    synopsis=bible.synopsis,
                    target_eps=kwargs.get("target_eps", 50),
                    style_dna=style_dna,
                    marketing_data=mkt_data,
                    created_at=datetime.now(),
                )
                self.session.add(book_obj)
                await self.session.flush()
                book_id = book_obj.id
                branch_id = None

            ws_data = bible.world_settings.model_dump()
            if not branch_id:
                branch_obj = Branch(book_id=book_id, name="Main", created_at=datetime.now())
                self.session.add(branch_obj)
                await self.session.flush()
                branch_id = branch_obj.id
                book_obj.current_branch_id = branch_id

            ws_data.update(
                {
                    "story_direction": bible.story_direction,
                    "dynamic_pacing_graph": [p.model_dump() for p in bible.dynamic_pacing_graph],
                    "villain_parallel_timeline": bible.villain_parallel_timeline,
                    "arcs": [a.model_dump() for a in bible.arcs],
                    "full_story_roadmap": [r.model_dump() for r in bible.full_story_roadmap],
                    "dna": getattr(bible, "dna").model_dump()
                    if hasattr(bible, "dna") and getattr(bible, "dna")
                    else None,
                }
            )

            bible_obj = Bible(
                book_id=book_id,
                settings=json.dumps(ws_data, ensure_ascii=False),
                version=1,
                last_updated=datetime.now(),
            )
            self.session.add(bible_obj)

            # Characters
            chars = []
            chars.append(
                Character(
                    book_id=book_id,
                    name=bible.mc_profile.name,
                    role="主人公",
                    registry_data=json.dumps(bible.mc_profile.model_dump(), ensure_ascii=False),
                )
            )
            for s in bible.sub_characters:
                chars.append(
                    Character(
                        book_id=book_id,
                        name=s.name,
                        role=s.role,
                        registry_data=json.dumps(s.model_dump(), ensure_ascii=False),
                    )
                )
            self.session.add_all(chars)

            # Plots: 話数ごとの SELECT を N 回重ねるのではなく一括 UPSERT する。
            # 旧実装は SELECT → 未存在なら INSERT で、同時保存時に
            # UNIQUE(book_id, branch_id, ep_num) 制約で後着が落ちていた。
            # 既存行も「計画済みテンプレート」で上書きする点は旧実装と同じ。
            target_eps = kwargs.get("target_eps", 50)
            bind = self.session.get_bind()
            dialect = bind.dialect.name
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as _insert
            else:
                from sqlalchemy.dialects.sqlite import insert as _insert
            stmt = _insert(Plot).values(
                [
                    {
                        "book_id": book_id,
                        "branch_id": branch_id,
                        "ep_num": ep,
                        "title": f"第{ep}話 (TBD)",
                        "summary": "andang...",
                        "status": "planned",
                        "current_chain_phase": "Hate",
                    }
                    for ep in range(1, target_eps + 1)
                ]
            )
            await self.session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[Plot.book_id, Plot.branch_id, Plot.ep_num],
                    set_={
                        "title": stmt.excluded.title,
                        "summary": stmt.excluded.summary,
                        "status": stmt.excluded.status,
                        "current_chain_phase": stmt.excluded.current_chain_phase,
                    },
                )
            )

            return book_id
        except Exception as e:
            logger.error(f"Failed to save full world bible: {e}\n{traceback.format_exc()}")
            raise


async def add_pending_setting(
    self,
    book_id: int,
    category: str,
    target: str,
    fact: str,
    evidence: str,
    confidence: float,
    priority: int = 1,
) -> None:
    """本文から抽出された仮設定を保存する"""
    pending = BiblePendingSetting(
        book_id=book_id,
        category=category,
        target=target,
        fact=fact,
        evidence=evidence,
        confidence=confidence,
        priority=priority,
        status="pending",
    )
    self.session.add(pending)


async def get_pending_settings(self, book_id: int) -> list[BiblePendingSetting]:
    """未承認の仮設定一覧を取得する"""
    result = await self.session.execute(
        select(BiblePendingSetting).where(
            BiblePendingSetting.book_id == book_id, BiblePendingSetting.status == "pending"
        )
    )
    return list(result.scalars().all())


async def resolve_pending_setting(self, setting_id: int, status: str) -> None:
    """仮設定を承認(approved)または拒絶(rejected)する"""
    result = await self.session.execute(
        select(BiblePendingSetting).where(BiblePendingSetting.id == setting_id)
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.status = status
        from datetime import datetime

        setting.resolved_at = datetime.now()
