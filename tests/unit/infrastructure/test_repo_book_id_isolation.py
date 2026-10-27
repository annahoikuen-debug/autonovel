"""tests/unit/infrastructure/test_repo_book_id_isolation.py.

`book_id` スコープの欠落によるクロステナント読み出しの回帰テスト。

このテストが固定する問題
----------------------
``chapters`` / ``plots`` テーブルの一意制約は ``UNIQUE(book_id, branch_id, ep_num)``
だが、``branch_id`` は **作品ごとに固有ではなく** 全作品で既定値 1 が使われる
（``src/agents/writing/generator.py`` の ``self.branch_id = 1``、
``src/backend/database/series_loader.py`` の ``Chapter(book_id=..., branch_id=1, ...)``）。

そのため ``WHERE branch_id = ? AND ep_num = ?`` だけで引くと:

* 他作品に同 (branch_id, ep_num) の行が 1 件だけあれば、それを **返してしまう**
  （クロステナント読み出し）
* 2 件以上あれば ``scalar_one_or_none()`` が ``MultipleResultsFound`` で 500 になる

``get_chapter`` / ``get_plot`` / ``get_all_plots`` はいずれもこの形だった。
本テストは「同一 branch_id / 同一 ep_num の行が別作品に存在する」状況を明示的に作り、
``book_id`` を渡した取得が他作品の行を返さないことを固定する。
"""

from __future__ import annotations

import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

import src.backend.database.models  # noqa: F401,E402  (Base 定義の読込)
import src.backend.database.models_tenant  # noqa: F401,E402
import src.infrastructure.database.models  # noqa: F401,E402
from src.backend.database.models import Book, Chapter, Plot  # noqa: E402
from src.infrastructure.database.models.base_orm import Base  # noqa: E402
from src.infrastructure.repositories.chapter import ChapterRepository  # noqa: E402
from src.infrastructure.repositories.plot import PlotRepository  # noqa: E402

# 2 作品 x 同一 branch_id / 同一 ep_num。branch_id は全作品で 1（= 実際の既定値）。
BOOK_A = 1
BOOK_B = 2
BRANCH = 1
EP_NUM = 5


@pytest.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'isolation.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


def _seed(session: AsyncSession) -> None:
    """BOOK_A と BOOK_B が同じ branch_id / ep_num を共有する状態を作る。"""
    for book_id, tag in ((BOOK_A, "A"), (BOOK_B, "B")):
        session.add(Book(id=book_id, title=f"{tag}の作品"))
        session.add(
            Chapter(
                book_id=book_id,
                branch_id=BRANCH,
                ep_num=EP_NUM,
                title=f"{tag}第{EP_NUM}話",
                content=f"{tag}の本文",
                summary=f"{tag}の要約",
                world_state="{}",
                trinity_review_log="{}",
            )
        )
        session.add(
            Plot(
                book_id=book_id,
                branch_id=BRANCH,
                ep_num=EP_NUM,
                title=f"{tag}プロット{EP_NUM}",
                summary=f"{tag}の要約",
                thought_process="",
                detailed_blueprint="",
                next_hook="{}",
                scenes="[]",
                healed_fields="[]",
                status="planned",
            )
        )


class TestChapterBookScoping:
    async def test_get_chapter_returns_own_book_row(self, session: AsyncSession) -> None:
        """``get_chapter(1, 5, book_id=A)`` は A の章を返す（B ではない）。"""
        _seed(session)
        await session.commit()

        repo = ChapterRepository(session)
        chapter = await repo.get_chapter(BRANCH, EP_NUM, book_id=BOOK_A)

        assert chapter is not None, "A の章が取得できなかった"
        assert chapter.content == "Aの本文", "他作品 (B) の章が返ってきた"

    async def test_get_chapter_never_returns_other_book_row(self, session: AsyncSession) -> None:
        """B 側も同じ形で自分の行を返す（片側だけ直しただけでは不十分）。"""
        _seed(session)
        await session.commit()

        repo = ChapterRepository(session)
        chapter = await repo.get_chapter(BRANCH, EP_NUM, book_id=BOOK_B)

        assert chapter is not None
        assert chapter.content == "Bの本文", "他作品 (A) の章が返ってきた"

    async def test_two_books_coexist_without_duplicate_error(self, session: AsyncSession) -> None:
        """``book_id`` を渡せば両方の行が同時に存在しても例外にならない。

        旧実装は ``book_id`` を条件に入れないため 2 件ヒットして
        ``MultipleResultsFound``（= HTTP 500）になっていた。
        """
        _seed(session)
        await session.commit()

        repo = ChapterRepository(session)
        a = await repo.get_chapter(BRANCH, EP_NUM, book_id=BOOK_A)
        b = await repo.get_chapter(BRANCH, EP_NUM, book_id=BOOK_B)

        assert a is not None and b is not None
        assert a.content != b.content


class TestPlotBookScoping:
    async def test_get_plot_returns_own_book_row(self, session: AsyncSession) -> None:
        _seed(session)
        await session.commit()

        repo = PlotRepository(session)
        plot = await repo.get_plot(BRANCH, EP_NUM, book_id=BOOK_A)

        assert plot is not None, "A のプロットが取得できなかった"
        assert plot.title == "Aプロット5", "他作品 (B) のプロットが返ってきた"

    async def test_get_plot_never_returns_other_book_row(self, session: AsyncSession) -> None:
        _seed(session)
        await session.commit()

        repo = PlotRepository(session)
        plot = await repo.get_plot(BRANCH, EP_NUM, book_id=BOOK_B)

        assert plot is not None
        assert plot.title == "Bプロット5", "他作品 (A) のプロットが返ってきた"

    async def test_get_all_plots_returns_only_requested_book(self, session: AsyncSession) -> None:
        """一覧取得は作品単位で完全に分離される（他作品が混ざらない）。"""
        _seed(session)
        await session.commit()

        repo = PlotRepository(session)
        plots = await repo.get_all_plots(BRANCH, book_id=BOOK_A)

        assert len(plots) == 1, f"A のプロット 1 件のみのはずが {len(plots)} 件返った"
        assert plots[0].title == "Aプロット5", "他作品のプロットが一覧に混ざっている"

    async def test_get_all_plots_other_book_isolated(self, session: AsyncSession) -> None:
        _seed(session)
        await session.commit()

        repo = PlotRepository(session)
        plots = await repo.get_all_plots(BRANCH, book_id=BOOK_B)

        assert len(plots) == 1
        assert plots[0].title == "Bプロット5", "他作品のプロットが一覧に混ざっている"
