"""伏線自動設置フック（``bible_service._plant_foreshadowings_from_roadmap``）の統合テスト。

検証する契約:

- **フラグ OFF（既定）なら DB 副作用ゼロ**（ロールバック可能性）
- **フラグ ON なら UoW トランザクション内に設置される**
  （book 行は未コミットのため、別セッションからは見えない＝同一 TX であること）
- **UoW コミットで永続化される**（原子的に book / Bible / 伏線が確定する）
- **冪等**（同じ roadmap を 2 回流しても行が増えない）
- **設置失敗は Bible 生成を落とさない**（非致命）
- **配線**: ``_create_ultra_fast_plan`` / ``_create_standard_plan`` が
  ``save_full_world_bible`` の直後にフックを呼ぶこと（AST で固定）

なおフックは **現在の UoW セッションを使う**設計が必須である。
別セッションで設置すると ``PRAGMA foreign_keys=ON`` の下で
未コミットの book 行を参照できず ``database is locked`` になる
（実測済み）。本テストはファイルベースの SQLite で接続を分離し、
その前提を固定する。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from src.backend.database.core import DatabaseManager
from src.backend.database.models_foreshadowing import ForeshadowingModel
from src.backend.database.repository import DataRepositoryFacade
from src.backend.database.uow import UnitOfWork
from src.infrastructure.database.models.base_orm import Base
from src.models.plot import RoadmapItem
from src.services.bible_service import WorldBibleGenerator

REPO_ROOT = Path(__file__).resolve().parents[3]
BIBLE_SERVICE_PATH = REPO_ROOT / "src" / "services" / "bible_service.py"


def _tables_with_fk_closure(table) -> list:
    collected: list = []
    stack = [table]
    while stack:
        current = stack.pop()
        if current in collected:
            continue
        collected.append(current)
        for fk in current.foreign_keys:
            stack.append(fk.column.table)
    return collected


def _roadmap_items() -> list[RoadmapItem]:
    return [
        RoadmapItem(
            ep_num=1,
            one_line_summary="遺品が発見される",
            resolution_style="Cheat",
            antagonist_status="暗躍する",
            foreshadowing_setup="謎の剣が出現する",
        ),
        RoadmapItem(
            ep_num=2,
            one_line_summary="静かな日常",
            resolution_style="Focus_Drama",
            antagonist_status="潜伏している",
            foreshadowing_setup="なし",
        ),
        RoadmapItem(
            ep_num=3,
            one_line_summary="過去が表紙される",
            resolution_style="Logic",
            antagonist_status="行動を開始する",
            foreshadowing_setup="消えた手紙の行方",
        ),
    ]


class _FakeBible:
    """``WorldBible`` のうちフックが読む ``full_story_roadmap`` だけを持つ代用。"""

    def __init__(self, roadmap: list[RoadmapItem]) -> None:
        self.full_story_roadmap = roadmap


@pytest.fixture
async def db_env(tmp_path):
    db_file = tmp_path / "planting_hook.db"
    db_url = f"sqlite:///{db_file}"
    db = DatabaseManager(db_url)

    engine = create_async_engine(db_url.replace("sqlite:///", "sqlite+aiosqlite:///"))
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_tables_with_fk_closure(ForeshadowingModel.__table__),
        )
    await engine.dispose()

    repo = DataRepositoryFacade(db)
    generator = WorldBibleGenerator(
        repo, llm=None, pm=None, debate=None, marketing=None, auditor=None
    )
    try:
        yield db, repo, generator
    finally:
        await db.engine.dispose()


async def _count_foreshadowings(db: DatabaseManager, book_id: int) -> int:
    """**別セッション**から件数を数える（コミット済みの行だけ見える）。"""
    async with db.get_session() as session:
        result = await session.execute(
            select(ForeshadowingModel).where(ForeshadowingModel.book_id == book_id)
        )
        return len(result.scalars().all())


async def _insert_book(session, book_id: int) -> None:
    await session.execute(
        insert(Base.metadata.tables["books"]).values(
            id=book_id,
            title="フック検証作品",
            mode="easy",
            genre="",
            concept="",
            synopsis="",
            catchcopy="",
            style_dna="",
            status="draft",
            marketing_data="",
        )
    )


# ── フラグ OFF ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hook_flag_off_creates_no_rows(db_env, monkeypatch):
    """フラグ OFF（既定）なら設置フックは DB に一切書き込まない。"""
    db, repo, generator = db_env
    monkeypatch.delenv("FORESHADOW_PLANTING", raising=False)

    async with UnitOfWork(db) as uow:
        await _insert_book(uow.session, book_id=1)
        await generator._plant_foreshadowings_from_roadmap(
            book_id=1,
            bible_obj=_FakeBible(_roadmap_items()),
            total_episodes=10,
        )

    assert await _count_foreshadowings(db, book_id=1) == 0


# ── フラグ ON：同一 UoW トランザクション ──────────────────


@pytest.mark.asyncio
async def test_hook_flag_on_plants_inside_uow_transaction(db_env, monkeypatch):
    """フラグ ON なら **UoW と同じトランザクション** に設置される。

    UoW コミット前は別セッションから行が見えず（未コミット）、
    UoW を抜けた瞬点で行が永続化される。
    """
    db, repo, generator = db_env
    monkeypatch.setenv("FORESHADOW_PLANTING", "1")

    async with UnitOfWork(db) as uow:
        await _insert_book(uow.session, book_id=2)
        await generator._plant_foreshadowings_from_roadmap(
            book_id=2,
            bible_obj=_FakeBible(_roadmap_items()),
            total_episodes=10,
        )
        # 同一トランザクション内なので flush 済み行は自分のセッションから見える
        in_tx = await uow.session.execute(
            select(ForeshadowingModel).where(ForeshadowingModel.book_id == 2)
        )
        assert len(in_tx.scalars().all()) == 2
        # 別セッション（別接続）からは未コミットなので見えない
        assert await _count_foreshadowings(db, book_id=2) == 0

    # UoW コミット後に別セッションから見える
    assert await _count_foreshadowings(db, book_id=2) == 2


@pytest.mark.asyncio
async def test_hook_planted_rows_carry_roadmap_content(db_env, monkeypatch):
    """設置された行が roadmap の内容（タイトル/話数/キーワード）を持つこと。"""
    db, repo, generator = db_env
    monkeypatch.setenv("FORESHADOW_PLANTING", "1")

    async with UnitOfWork(db) as uow:
        await _insert_book(uow.session, book_id=3)
        await generator._plant_foreshadowings_from_roadmap(
            book_id=3,
            bible_obj=_FakeBible(_roadmap_items()),
            total_episodes=10,
        )

    async with db.get_session() as session:
        result = await session.execute(
            select(ForeshadowingModel)
            .where(ForeshadowingModel.book_id == 3)
            .order_by(ForeshadowingModel.planted_episode)
        )
        rows = list(result.scalars().all())

    assert [r.title for r in rows] == ["謎の剣が出現する", "消えた手紙の行方"]
    assert [r.planted_episode for r in rows] == [1, 3]
    # 「なし」行は設置されない（foreshadowing_setup="なし" はスキップ）
    assert all(r.status == "planted" for r in rows)


# ── 冪等性 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hook_is_idempotent_across_uow_runs(db_env, monkeypatch):
    """同じ roadmap で 2 回 Bible 生成しても行が増えない（冪等）。

    book は 1 回だけ作成し（2 回目の「生成」は既存作品に対する
    再実行を想定）、フックを別々の UoW で 2 回走らせる。
    """
    db, repo, generator = db_env
    monkeypatch.setenv("FORESHADOW_PLANTING", "1")

    async with UnitOfWork(db) as uow:
        await _insert_book(uow.session, book_id=4)

    for _ in range(2):
        async with UnitOfWork(db) as uow:
            await generator._plant_foreshadowings_from_roadmap(
                book_id=4,
                bible_obj=_FakeBible(_roadmap_items()),
                total_episodes=10,
            )

    assert await _count_foreshadowings(db, book_id=4) == 2


# ── 非致命性 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hook_failure_is_non_fatal(db_env, monkeypatch):
    """設置が失敗しても例外は伝播しない（Bible 生成は継続）。"""
    import src.services.bible_service as bible_service_module

    db, repo, generator = db_env
    monkeypatch.setenv("FORESHADOW_PLANTING", "1")

    async def _exploding_planted(*args, **kwargs):
        raise RuntimeError("simulated planting failure")

    monkeypatch.setattr(bible_service_module, "plant_from_roadmap", _exploding_planted)

    async with UnitOfWork(db) as uow:
        await _insert_book(uow.session, book_id=5)
        # 例外が伝播したらこのテストは失敗する
        await generator._plant_foreshadowings_from_roadmap(
            book_id=5,
            bible_obj=_FakeBible(_roadmap_items()),
            total_episodes=10,
        )

    assert await _count_foreshadowings(db, book_id=5) == 0


@pytest.mark.asyncio
async def test_hook_without_uow_falls_back_to_own_session(db_env, monkeypatch):
    """UoW 外（防御経路）では独自セッションで設置し自前コミットする。

    この経路では book は既にコミット済みという前提なので、
    別セッションでも FK は満足される。
    """
    db, repo, generator = db_env
    monkeypatch.setenv("FORESHADOW_PLANTING", "1")

    # book を先にコミットしておく（UoW 外の前提を再現）
    async with UnitOfWork(db) as uow:
        await _insert_book(uow.session, book_id=6)

    # UoW なしで直接呼ぶ → フォールバック経路
    await generator._plant_foreshadowings_from_roadmap(
        book_id=6,
        bible_obj=_FakeBible(_roadmap_items()),
        total_episodes=10,
    )

    assert await _count_foreshadowings(db, book_id=6) == 2


# ── 配線（AST ゲート）──────────────────────────────────────


def _function_names_calling(tree: ast.Module, target_attr: str) -> set[str]:
    """`self.<target_attr>(...)` を呼び出している関数名を列挙する。"""
    callers: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == target_attr
            ):
                callers.add(node.name)
    return callers


def test_plan_methods_call_planting_hook():
    """両プラン生成メソッドが ``save_full_world_bible`` の後にフックを呼ぶこと。

    フックが外れると「フラグを ON にしても伏線が設置されない」
    静默故障になるため、AST で配線を固定する。
    """
    tree = ast.parse(BIBLE_SERVICE_PATH.read_text(encoding="utf-8"))
    callers = _function_names_calling(tree, "_plant_foreshadowings_from_roadmap")

    assert "_create_ultra_fast_plan" in callers, (
        "_create_ultra_fast_plan が伏線設置フックを呼んでいない"
    )
    assert "_create_standard_plan" in callers, (
        "_create_standard_plan が伏線設置フックを呼んでいない"
    )


def test_hook_uses_current_uow_session_not_separate_session():
    """フックが ``current_uow`` 経由の同一セッションを使うこと（FK 安全性の固定）。

    別セッション（``get_session()`` を直接使う）実装に戻ると
    ``PRAGMA foreign_keys=ON`` の下で ``database is locked`` になる。
    """
    tree = ast.parse(BIBLE_SERVICE_PATH.read_text(encoding="utf-8"))

    hook_def = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_plant_foreshadowings_from_roadmap"
        ):
            hook_def = node
            break
    assert hook_def is not None, "_plant_foreshadowings_from_roadmap が存在しない"

    source_segment = ast.get_source_segment(
        BIBLE_SERVICE_PATH.read_text(encoding="utf-8"), hook_def
    )
    assert "current_uow" in source_segment, (
        "フックが current_uow 経由のセッションを使っていない"
    )
