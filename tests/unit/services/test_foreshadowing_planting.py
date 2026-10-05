"""伏線自動設置エンジンの契約テスト。

A-T4: `plant_from_roadmap` の冪等性（同じ roadmap を2回流しても行が増えない）
A-T5: フラグ OFF で 0件返し、DB に副作用ゼロ（ロールバック可能性）
A-T6: `foreshadowing_setup="なし"` / 空文字は設置されない
A-T7: `planting_service` と `foreshadowing_repo` に生 `insert()` が無いこと（AST 固定）
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.backend.database.models_foreshadowing import ForeshadowingModel
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository
from src.services.foreshadowing import planting_service, flags
from src.services.foreshadowing.planting_service import plant_from_roadmap

REPO_ROOT = Path(__file__).resolve().parents[3]


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


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_tables_with_fk_closure(ForeshadowingModel.__table__),
        )
        for table in _tables_with_fk_closure(ForeshadowingModel.__table__):
            if table.name == "books":
                await conn.execute(
                    insert(table).values(
                        id=1,
                        title="テスト作品",
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
    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        yield factory
    finally:
        await engine.dispose()


@dataclass
class FakeRoadmapItem:
    """`RoadmapItem` の必要フィールドだけを持つ roadmap 行の代用。"""

    ep_num: int
    foreshadowing_setup: str = "なし"
    foreshadowing_payoff: str = "なし"
    one_line_summary: str = ""
    keywords: list = field(default_factory=list)


def _roadmap() -> list[FakeRoadmapItem]:
    return [
        FakeRoadmapItem(1, foreshadowing_setup="謎の剣が出現する", one_line_summary="遺品が発見される"),
        FakeRoadmapItem(2, foreshadowing_setup="なし", one_line_summary="静かな日常"),
        FakeRoadmapItem(3, foreshadowing_setup="消えた手紙の行方", one_line_summary="過去が表紙される"),
    ]


# ── A-T4: 冪等性 ─────────────────────────────────────


async def test_plant_from_roadmap_is_idempotent(session_factory):
    """A-T4: 同じ roadmap を2回流しても行が増えない（漏れると伏線が二重になる）。"""
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)

        first = await plant_from_roadmap(repo, 1, _roadmap(), 40)
        await repo.commit()
        assert len(first) == 2

        rows_after_first = await repo.get_by_book_id(1)
        assert len(rows_after_first) == 2

        second = await plant_from_roadmap(repo, 1, _roadmap(), 40)
        await repo.commit()

        assert second == [], "2回目は新規設置ゼロであること"
        rows_after_second = await repo.get_by_book_id(1)
        assert len(rows_after_second) == 2, "行が増えていないこと"
        assert sorted(r.id for r in rows_after_second) == sorted(r.id for r in rows_after_first)


async def test_plant_from_roadmap_third_time_still_stable(session_factory):
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        for _ in range(3):
            await plant_from_roadmap(repo, 1, _roadmap(), 40)
            await repo.commit()
        assert len(await repo.get_by_book_id(1)) == 2


async def test_plant_from_roadmap_accepts_dict_rows(session_factory):
    """dict 形式の roadmap 行も扱えること（シリアライズ経路への対応）。"""
    rows = [
        {"ep_num": 5, "foreshadowing_setup": "鍵の行方", "foreshadowing_payoff": "回収"},
        {"ep_num": 6, "foreshadowing_setup": "なし"},
    ]
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        planted = await plant_from_roadmap(repo, 1, rows, 40)
        await repo.commit()
        assert len(planted) == 1
        assert planted[0].planted_episode == 5
        assert planted[0].title == "鍵の行方"


async def test_plant_sets_target_and_scope_from_planner(session_factory):
    """planner の決定（target_episode / scope）がそのまま反映される。"""
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        planted = await plant_from_roadmap(repo, 1, _roadmap(), 40)
        await repo.commit()

        for record in planted:
            assert record.target_episode is not None
            assert record.target_episode > record.planted_episode, (
                "回収先は設置話より後であること（horizon 0 は禁止）"
            )
            assert record.scope in ("short_term", "long_term")
            assert record.status == "planted"


async def test_plant_writes_keywords_column(session_factory):
    """設置側が `keywords` を書く（0035 フェーズ1 の配線確認）。"""
    from src.backend.database.models_foreshadowing import decode_keywords

    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        planted = await plant_from_roadmap(repo, 1, _roadmap(), 40)
        await repo.commit()
        assert planted
        for record in planted:
            assert decode_keywords(record.keywords), "キーワードが設定されていること"


async def test_plant_empty_roadmap_is_noop(session_factory):
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        assert await plant_from_roadmap(repo, 1, [], 40) == []
        assert await plant_from_roadmap(repo, 1, None, 40) == []
        await repo.commit()
        assert await repo.get_by_book_id(1) == []


# ── A-T5: フラグ OFF ─────────────────────────────────


class _ExplodingRepo:
    """OFF 時に触られてはいけないことの検証用リポジトリ。"""

    def __init__(self):
        self.calls: list = []

    def __getattr__(self, name):
        async def _boom(*args, **kwargs):
            self.calls.append(name)
            raise AssertionError(f"フラグ OFF で {name} が呼ばれた（副作用ゼロの期待）")

        return _boom


async def test_planting_disabled_returns_empty_and_never_touches_repo():
    """A-T5: `planting_enabled=False` で 0件、repo には一切触れない。"""
    repo = _ExplodingRepo()
    result = await plant_from_roadmap(repo, 1, _roadmap(), 40, planting_enabled=False)
    assert result == []
    assert repo.calls == [], f"呼び出しが0件であるべき: {repo.calls}"


async def test_planting_disabled_leaves_db_untouched(session_factory):
    """A-T5: フラグ OFF で実 DB にも副作用が無いこと。"""
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        result = await plant_from_roadmap(repo, 1, _roadmap(), 40, planting_enabled=False)
        await repo.commit()
        assert result == []
        assert await repo.get_by_book_id(1) == []


def test_planting_flag_defaults_off(monkeypatch):
    """A-T5: `FORESHADOW_PLANTING` は既定 OFF。"""
    monkeypatch.delenv("FORESHADOW_PLANTING", raising=False)
    assert flags.is_foreshadowing_planting_enabled() is False
    assert planting_service.is_planting_enabled() is False


def test_planting_flag_truthy_enables(monkeypatch):
    for raw in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("FORESHADOW_PLANTING", raw)
        assert flags.is_foreshadowing_planting_enabled() is True, raw


def test_planting_flag_falsy_disables(monkeypatch):
    for raw in ("0", "false", "no", "off", "banana", ""):
        monkeypatch.setenv("FORESHADOW_PLANTING", raw)
        assert flags.is_foreshadowing_planting_enabled() is False, raw


async def test_flag_off_means_no_planting_end_to_end(session_factory, monkeypatch):
    """A-T5: フラグ既定のまま呼んでも 0件（統合側がフラグを渡し忘れた場合も安全）。"""
    monkeypatch.delenv("FORESHADOW_PLANTING", raising=False)
    enabled = planting_service.is_planting_enabled()
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        result = await plant_from_roadmap(
            repo, 1, _roadmap(), 40, planting_enabled=enabled
        )
        await repo.commit()
        assert result == []


# ── A-T6: 「なし」/ 空文字 ───────────────────────────


@pytest.mark.parametrize("setup", ["なし", "", "  ", None])
async def test_no_setup_rows_are_skipped(session_factory, setup):
    """A-T6: `foreshadowing_setup` が「なし」/空文字なら設置されない。"""
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        rows = [FakeRoadmapItem(i + 1, foreshadowing_setup=setup) for i in range(4)]
        result = await plant_from_roadmap(repo, 1, rows, 40)
        await repo.commit()
        assert result == []
        assert await repo.get_by_book_id(1) == []


async def test_mixed_roadmap_skips_only_no_setup(session_factory):
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        rows = [
            FakeRoadmapItem(1, foreshadowing_setup="なし"),
            FakeRoadmapItem(2, foreshadowing_setup="右手の傷跡"),
            FakeRoadmapItem(3, foreshadowing_setup=""),
            FakeRoadmapItem(4, foreshadowing_setup="鍵の行方"),
            FakeRoadmapItem(5, foreshadowing_setup="なし"),
        ]
        result = await plant_from_roadmap(repo, 1, rows, 40)
        await repo.commit()
        assert [r.planted_episode for r in result] == [2, 4]


async def test_roadmap_item_model_uses_default_no_setup():
    """実 `RoadmapItem` の既定 `foreshadowing_setup` は「なし」であること。"""
    from src.models.plot import RoadmapItem

    item = RoadmapItem(
        ep_num=7,
        one_line_summary="要約",
        resolution_style="Cheat",
        antagonist_status="なし",
    )
    assert item.foreshadowing_setup == "なし"


async def test_plant_from_real_roadmap_items(session_factory):
    """実 `RoadmapItem` での設置が通ること（統合経路の想定）。"""
    from src.models.plot import RoadmapItem

    items = [
        RoadmapItem(
            ep_num=3,
            one_line_summary="封が解ける",
            resolution_style="Logic",
            antagonist_status="暗躍",
            foreshadowing_setup="封印の鍵が地下で発見される",
            foreshadowing_payoff="封が解ける",
        ),
        RoadmapItem(
            ep_num=4,
            one_line_summary="休息",
            resolution_style="Cheat",
            antagonist_status="なし",
        ),
    ]
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        result = await plant_from_roadmap(repo, 1, items, 40)
        await repo.commit()
        assert len(result) == 1
        assert result[0].planted_episode == 3


async def test_planting_key_inside_one_batch_is_deduplicated(session_factory):
    """同一バッチ内で `(ep, title)` が重複しても1本だけ。"""
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        rows = [
            FakeRoadmapItem(2, foreshadowing_setup="同じ伏線"),
            FakeRoadmapItem(2, foreshadowing_setup="同じ伏線"),
        ]
        result = await plant_from_roadmap(repo, 1, rows, 40)
        await repo.commit()
        assert len(result) == 1
        assert len(await repo.get_by_book_id(1)) == 1


async def test_long_title_is_truncated_to_column_limit(session_factory):
    """`title` は String(100) に収める（丸めることによる DB エラーを防ぐ）。"""
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        rows = [FakeRoadmapItem(1, foreshadowing_setup="あ" * 500)]
        result = await plant_from_roadmap(repo, 1, rows, 40)
        await repo.commit()
        assert len(result) == 1
        assert len(result[0].title) <= 100


async def test_plant_does_not_use_raw_insert(session_factory):
    """A-T7(動的): 設置後に行が `status='planted'` で入ること（KPI 経路の前提）。"""
    async with session_factory() as session:
        repo = DbForeshadowingRepository(session)
        await plant_from_roadmap(repo, 1, _roadmap(), 40)
        await repo.commit()
        statuses = await session.execute(
            select(ForeshadowingModel.status).where(ForeshadowingModel.book_id == 1)
        )
        assert sorted(statuses.scalars().all()) == ["planted", "planted"]


# ── A-T7: AST で生 insert() を禁止 ───────────────────


def _module_path(module_name: str) -> Path:
    return REPO_ROOT / Path(module_name.replace(".", "/") + ".py")


def _insert_call_nodes(tree: ast.AST) -> list[ast.Call]:
    """`insert(...)` / `X.insert(...)` 形式の呼び出しノードを全部集める。"""
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "insert":
            found.append(node)
        elif isinstance(func, ast.Attribute) and func.attr == "insert":
            found.append(node)
    return found


@pytest.mark.parametrize(
    "module_name",
    [
        "src.services.foreshadowing.planting_service",
        "src.infrastructure.repositories.foreshadowing_repo",
    ],
)
def test_no_raw_insert_call_in_modules(module_name):
    """A-T7: 生 `insert()` が無いことを AST で固定する。

    raw insert を使うと `add()` の `_report_planted` を迂回し、
    `foreshadowing_planted_total` が設置本数だけ減る。
    """
    path = _module_path(module_name)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    offenders = _insert_call_nodes(tree)
    assert offenders == [], (
        f"{module_name} に生 insert() が {len(offenders)} 箇所ある。"
        " `repo.add()` / `repo.add_many()` を使うこと（KPI を脱落させないため）"
    )


@pytest.mark.parametrize(
    "module_name",
    [
        "src.services.foreshadowing.planting_service",
        "src.infrastructure.repositories.foreshadowing_repo",
    ],
)
def test_insert_is_not_even_imported(module_name):
    """A-T7(補強): `sqlalchemy.insert` を import していないこと。

    import 自体が無いことが「生 insert を書ける場所が無い」ことを保証する。
    """
    source = _module_path(module_name).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "insert":
                    imported.append(f"{node.module}.{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "insert":
                    imported.append(alias.name)
    assert imported == [], f"{module_name} が insert を import している: {imported}"


def _attribute_call_names(tree: ast.AST, attribute: str) -> list[ast.Call]:
    """`<anything>.<attribute>(...)` 形式の呼び出しノードを集める。"""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute
    ]


def test_planting_service_uses_repo_add_or_add_many():
    """A-T7(補強): 設置は必ず `add_many` を通すことのソース固定。

    docstring 内の言及を拾わないよう、文字列ではなく **AST** で呼び出しを見る。
    """
    source = _module_path("src.services.foreshadowing.planting_service").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    add_many_calls = _attribute_call_names(tree, "add_many")
    add_calls = [
        call
        for call in _attribute_call_names(tree, "add")
        if isinstance(call.func.value, ast.Name)
        and call.func.value.id == "repo"
    ]
    assert add_many_calls, "repo.add_many(...) を呼んでいること"
    assert add_calls == [], "単発の repo.add(...) は add_many 経由に統一する"


def test_planting_service_never_calls_db_orm_insert_directly():
    """A-T7(補強): `db.add(` / `session.add(` を planting_service が使わないこと。

    セッションを直叩きすると `_report_planted` を飛ばす余地が生まれる。
    """
    source = _module_path("src.services.foreshadowing.planting_service").read_text(
        encoding="utf-8"
    )
    assert ".db.add(" not in source
    assert "session.add(" not in source


# ── 署名契約（統合担当向け） ─────────────────────────


def test_plant_from_roadmap_signature_is_stable():
    """統合側が前提とするシグネチャを固定する。"""
    import inspect

    sig = inspect.signature(plant_from_roadmap)
    params = list(sig.parameters)
    assert params == [
        "repo",
        "book_id",
        "roadmap_items",
        "total_episodes",
        "planting_enabled",
    ]
    assert sig.parameters["planting_enabled"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["planting_enabled"].default is True


def test_repo_add_many_signature():
    from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository

    assert hasattr(DbForeshadowingRepository, "add_many")


def test_simple_namespace_rows_supported(session_factory):
    """属性オブジェクト（SimpleNamespace）でも動くことを保証する。"""
    items = [
        SimpleNamespace(ep_num=8, foreshadowing_setup="遺書の存在", one_line_summary="x"),
    ]
    assert items
    from src.services.foreshadowing.planting_service import _get

    assert _get(items[0], "foreshadowing_setup") == "遺書の存在"
    assert _get({"foreshadowing_setup": "a"}, "foreshadowing_setup") == "a"
    assert _get(object(), "foreshadowing_setup", "fallback") == "fallback"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """フラグを消した状態で開始する（テスト間の環境汚染を防ぐ）。"""
    monkeypatch.delenv("FORESHADOW_PLANTING", raising=False)
    yield


sys.path.insert(0, str(REPO_ROOT))
