"""tests/unit/infrastructure/test_chapter_repository_book_scoping.py.

`ChapterRepository` の 3 メソッド（create / delete / get_all_non_anchor）が
``book_id`` で正しくスコープされていることの回帰テスト。

このテスト succeeding 理由（問題提起）
----------------------------------
このテストが固定する問題
----------------------

``chapters`` テーブルの一意制約は ``UNIQUE(book_id, branch_id, ep_num)``
（``src/backend/database/models.py``）だが、``branch_id`` は **作品ごとに固有では
なく** 全作品の既定値 1 が使われる（``src/agents/writing/generator.py`` の
``self.branch_id = 1``、``src/backend/database/series_loader.py`` の
``Chapter(book_id=book_id, branch_id=1, ...)``）。

そのため ``WHERE branch_id = ? AND ep_num = ?`` だけで章アルバムを引くと
他作品の行にマッチし、

* 1 件ならその行を自作品へ **移送**してしまう（クロステナント上書き）
* 2 件以上なら ``scalar_one_or_none()`` が ``MultipleResultsFound`` で 500 になる

同じ理由で ``delete_chapter`` は他作品の章を削除でき、
``get_all_non_anchor_chapters`` は他作品の本文を返していた。

旧実装（``src/backend/database/repository.py``）は正しく
``WHERE book_id = :book_id`` を掛けているため、移行時に分岐キーが
脱落していたことをこのテストで固定する。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

import src.backend.database.models  # noqa: F401,E402  (Base 定義の読込)
import src.backend.database.models_tenant  # noqa: F401,E402
import src.infrastructure.database.models  # noqa: F401,E402
from src.backend.database.models import Book, Chapter  # noqa: E402
from src.infrastructure.database.models.base_orm import Base  # noqa: E402
from src.infrastructure.repositories.chapter import ChapterRepository  # noqa: E402

# 2 作品 x 3 話。branch_id は全作品で 1（= 実際の既定値）。
BOOK_A = 1
BOOK_B = 2
BRANCH = 1

ORIGINAL_CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scope.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


def _seed(session: AsyncSession) -> None:
    """BOOK_A と BOOK_B が同じ branch_id / ep_num を共有する状態を作る。"""
    for book_id, tag in ((BOOK_A, "A"), (BOOK_B, "B")):
        session.add(Book(id=book_id, title=f"{tag}の作品"))
        for ep in (1, 2, 3):
            session.add(
                Chapter(
                    book_id=book_id,
                    branch_id=BRANCH,
                    ep_num=ep,
                    title=f"{tag}第{ep}話",
                    content=f"{tag}の本文{ep}",
                    summary=f"{tag}の要約{ep}",
                    killer_phrase=f"{tag}のキラーフレーズ{ep}",
                    ai_insight=f"{tag}のAI洞察{ep}",
                    world_state=f'{{"owner": "{tag}"}}',
                    trinity_review_log="{}",
                    created_at=ORIGINAL_CREATED_AT,
                )
            )


async def _counts(session: AsyncSession) -> dict[tuple[int, int], int]:
    from sqlalchemy import func, select

    result = await session.execute(
        select(Chapter.book_id, Chapter.ep_num, func.count(Chapter.id)).group_by(
            Chapter.book_id, Chapter.ep_num
        )
    )
    return {(row[0], row[1]): row[2] for row in result}


class TestCreateChapterScoping:
    async def test_does_not_hijack_other_book_chapter(self, session: AsyncSession) -> None:
        """他作品に同 (branch_id, ep_num) があっても、その行を奪わない。"""
        _seed(session)
        await session.commit()

        repo = ChapterRepository(session)
        await repo.create_chapter(
            book_id=BOOK_A,
            ep_num=1,
            title="A第1話(改訂)",
            content="改訂された本文",
            summary="改訂要約",
            killer_phrase=None,
            ai_insight="",
            world_state="{}",
            trinity_review_log="{}",
            created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            branch_id=BRANCH,
        )
        await session.commit()

        # 総行数は増えない（upsert であることも含意している）
        assert await _counts(session) == {
            (BOOK_A, 1): 1,
            (BOOK_A, 2): 1,
            (BOOK_A, 3): 1,
            (BOOK_B, 1): 1,
            (BOOK_B, 2): 1,
            (BOOK_B, 3): 1,
        }

        # BOOK_B の第1話は他人の資産。書き換わっていない。
        b1 = (
            await session.execute(
                Chapter.__table__.select().where(Chapter.book_id == BOOK_B).where(
                    Chapter.ep_num == 1
                )
            )
        ).mappings().first()
        assert b1["content"] == "Bの本文1", "他作品の本文が上書きされた"
        assert b1["title"] == "B第1話", "他作品のタイトルが上書きされた"

    async def test_updates_only_target_book(self, session: AsyncSession) -> None:
        _seed(session)
        await session.commit()

        repo = ChapterRepository(session)
        await repo.create_chapter(
            book_id=BOOK_B,
            ep_num=2,
            title="B第2話(改訂)",
            content="B改訂",
            summary="改訂",
            killer_phrase=None,
            ai_insight="",
            world_state="{}",
            trinity_review_log="{}",
            created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            branch_id=BRANCH,
        )
        await session.commit()

        a2 = (
            await session.execute(
                Chapter.__table__.select().where(Chapter.book_id == BOOK_A).where(
                    Chapter.ep_num == 2
                )
            )
        ).mappings().first()
        assert a2["content"] == "Aの本文2", "別作品の同一話番号が書き換わった"

    async def test_upsert_preserves_generated_metadata(self, session: AsyncSession) -> None:
        """保存時に未指定フィールド（生成済みメタデータ）を飛ばさない。"""
        _seed(session)
        await session.commit()

        repo = ChapterRepository(session)
        # ルーターと同じ呼び出し形状: 生成済みメタデータは渡さない
        await repo.create_chapter(
            book_id=BOOK_A,
            ep_num=1,
            title="A第1話(編集)",
            content="手書きで直した本文",
            summary="要約",
            branch_id=BRANCH,
        )
        await session.commit()

        row = (
            await session.execute(
                Chapter.__table__.select().where(Chapter.book_id == BOOK_A).where(
                    Chapter.ep_num == 1
                )
            )
        ).mappings().first()
        assert row["content"] == "手書きで直した本文", "本文の編集が反映されていない"
        assert row["killer_phrase"] == "Aのキラーフレーズ1", (
            "生成済みの killer_phrase が保存で消えた"
        )
        assert row["ai_insight"] == "AのAI洞察1", "生成済みの ai_insight が保存で消えた"
        assert row["world_state"] == '{"owner": "A"}', "world_state が保存で消えた"
        assert row["created_at"] == ORIGINAL_CREATED_AT, "作成日時が保存で上書きされた"

    async def test_legacy_none_metadata_call_is_safe(self, session: AsyncSession) -> None:
        """旧呼び出し形状（``killer_phrase=None`` など）でも既存値を消さない。"""
        _seed(session)
        await session.commit()

        repo = ChapterRepository(session)
        await repo.create_chapter(
            book_id=BOOK_A,
            ep_num=1,
            title="A第1話",
            content="本文",
            summary="要約",
            killer_phrase=None,
            world_state=None,
            trinity_review_log=None,
            created_at=None,
            branch_id=BRANCH,
        )
        await session.commit()

        row = (
            await session.execute(
                Chapter.__table__.select().where(Chapter.book_id == BOOK_A).where(
                    Chapter.ep_num == 1
                )
            )
        ).mappings().first()
        assert row["killer_phrase"] == "Aのキラーフレーズ1"
        assert row["world_state"] == '{"owner": "A"}'
        assert row["trinity_review_log"] == "{}"

    async def test_accepts_iso_string_created_at(self, session: AsyncSession) -> None:
        """``datetime.isoformat()`` の文字列を渡しても保存できる。

        ``CompatibleDateTime.process_bind_param`` は ``value.tzinfo`` を前提とするため、
        文字列のままだと StatementError になり旧呼び出し側が全滅していた。
        """
        _seed(session)
        await session.commit()

        repo = ChapterRepository(session)
        await repo.create_chapter(
            book_id=BOOK_A,
            ep_num=2,
            title="A第2話",
            content="本文",
            summary="要約",
            created_at=datetime(2026, 5, 5, 12, 30, tzinfo=timezone.utc).isoformat(),
            branch_id=BRANCH,
        )
        await session.commit()  # flush できていれば成功

        row = (
            await session.execute(
                Chapter.__table__.select().where(Chapter.book_id == BOOK_A).where(
                    Chapter.ep_num == 2
                )
            )
        ).mappings().first()
        assert row["created_at"] == datetime(2026, 5, 5, 12, 30, tzinfo=timezone.utc)


class TestDeleteChapterScoping:
    async def test_does_not_delete_other_book_chapter(self, session: AsyncSession) -> None:
        _seed(session)
        await session.commit()

        repo = ChapterRepository(session)
        await repo.delete_chapter(BOOK_A, 1, branch_id=BRANCH)
        await session.commit()

        assert await _counts(session) == {
            (BOOK_A, 2): 1,
            (BOOK_A, 3): 1,
            (BOOK_B, 1): 1,
            (BOOK_B, 2): 1,
            (BOOK_B, 3): 1,
        }

    async def test_delete_returns_rowcount(self, session: AsyncSession) -> None:
        """削除件数が分かるよう rowcount を返し、0 件は呼び出し側で 404 にできる。"""
        _seed(session)
        await session.commit()

        repo = ChapterRepository(session)
        deleted = await repo.delete_chapter(BOOK_A, 3, branch_id=BRANCH)
        await session.commit()
        assert deleted == 1

        missing = await repo.delete_chapter(BOOK_A, 99, branch_id=BRANCH)
        await session.commit()
        assert missing == 0, "存在しない章の削除が 1 件と-reported された"


class TestGetAllNonAnchorChaptersScoping:
    async def test_returns_only_requested_book(self, session: AsyncSession) -> None:
        _seed(session)
        await session.commit()

        repo = ChapterRepository(session)
        chapters = await repo.get_all_non_anchor_chapters(BOOK_A, branch_id=BRANCH)

        assert len(chapters) == 3
        assert all(c.content.startswith("Aの本文") for c in chapters), (
            "他作品の本文が混ざっている"
        )

    async def test_first_argument_is_treated_as_book_id(self, session: AsyncSession) -> None:
        """第1引数だけを渡した呼び出し（= book_id）でも作品単位で絞られる。

        実際の呼び出し側は ``episodes.py`` / ``chapters.py`` / ``export.py``
        が book_id のみを渡すため、これは必須の保証である。
        """
        _seed(session)
        await session.commit()

        repo = ChapterRepository(session)
        chapters = await repo.get_all_non_anchor_chapters(BOOK_B)

        assert len(chapters) == 3
        assert all(c.content.startswith("Bの本文") for c in chapters)

    async def test_excludes_anchor_chapters(self, session: AsyncSession) -> None:
        """名前に反して is_anchor 行を返さない（旧実装と同じ意味論）。"""
        _seed(session)
        session.add(
            Chapter(
                book_id=BOOK_A,
                branch_id=BRANCH,
                ep_num=9,
                title="アンカー",
                content="アンカー本文",
                is_anchor=True,
            )
        )
        await session.commit()

        repo = ChapterRepository(session)
        chapters = await repo.get_all_non_anchor_chapters(BOOK_A, branch_id=BRANCH)

        assert all(c.ep_num != 9 for c in chapters), "アンカー章が混ざっている"
