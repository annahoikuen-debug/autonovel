"""`foreshadowings.keywords` カラムと `add_many()` の契約テスト。

A-T1: `add(keywords=[...])` の往復一致（区切り文字を含むキーワードで壊れない）
A-T2: `keywords` 未指定（None）の `add()` は既存挙動を壊さない
A-T3: `add()` の既存の位置引数4つ呼び出しがそのまま動く
A-T8: `add_many()` が `add()` と同じ `_report_planted` を呼ぶ
"""
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.backend.database.models_foreshadowing import (
    ForeshadowingModel,
    decode_keywords,
    encode_keywords,
)
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository


def _tables_with_fk_closure(table) -> list:
    """対象テーブルと、その外部キーが参照するテーブルを推移的に集める。"""
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


@asynccontextmanager
async def create_test_db():
    """伏線テーブルを実 async SQLite に用意する。"""
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
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        yield session_factory
    finally:
        await engine.dispose()


# 区切り文字・引用符・制御文字を含むキーワード群。
# naive な `",".join()` なら必ず壊れる（往復一致しない）。
TRICKY_KEYWORDS = [
    ["謎の剣"],
    ["a,b", "c"],
    ["改行\n入り", "タブ\t入り"],
    ["引用符\"付き", "角括弧[付き]"],
    ["先頭空白 途中空白", " 両端  "],
    ["カンマ,カンマ", "単独,", ",先頭", "末尾,"],
    [" 戦闘 ", " "],
    ["『 Villain 』", "（ Org. ）"],
    [str(1), str(2)],
]


@pytest.mark.parametrize("keywords", TRICKY_KEYWORDS)
def test_encode_decode_roundtrip_is_lossless(keywords):
    """A-T1(前半): エンコード→デコードで元に戻せること。

    naive な join（`,`  区切り）だと `["a,b"]` が `["a", "b"]` に割れる。
    """
    encoded = encode_keywords(keywords)
    assert isinstance(encoded, str)
    assert decode_keywords(encoded) == [str(k) for k in keywords]


def test_encode_none_and_empty():
    assert encode_keywords(None) is None
    assert encode_keywords([]) is None
    assert decode_keywords(None) is None
    assert decode_keywords("") is None
    assert decode_keywords("   ") is None


def test_decode_never_raises_on_garbage():
    assert decode_keywords("not json") is None
    assert decode_keywords('{"a": 1}') is None
    assert decode_keywords(b'["x"]') == ["x"]
    assert decode_keywords('["already", "list"]') == ["already", "list"]


@pytest.mark.parametrize("keywords", TRICKY_KEYWORDS)
async def test_add_keywords_roundtrip_through_db(keywords):
    """A-T1(後半): `add(keywords=...)` が DB 往復でも一致すること。"""
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            record = await repo.add(
                book_id=1,
                title="伏線A",
                description="説明",
                planted_episode=1,
                keywords=keywords,
            )
            await repo.commit()

            fetched = await repo.get_by_id(record.id)
            assert fetched is not None
            assert decode_keywords(fetched.keywords) == [str(k) for k in keywords]
            assert fetched.keyword_list == [str(k) for k in keywords]


async def test_add_without_keywords_stays_null():
    """A-T2: `keywords` 未指定（None）は NULL のままで、既存挙動を壊さない。"""
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            record = await repo.add(
                book_id=1, title="伏線B", description="説明", planted_episode=2
            )
            await repo.commit()

            assert record.keywords is None
            assert record.keyword_list == []

            fetched = await repo.get_by_id(record.id)
            assert fetched.keywords is None
            assert decode_keywords(fetched.keywords) is None


async def test_add_explicit_none_keywords():
    """A-T2: 明示的に None を渡しても NULL。"""
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            record = await repo.add(
                book_id=1,
                title="伏線C",
                description="説明",
                planted_episode=3,
                target_episode=8,
                keywords=None,
            )
            await repo.commit()
            assert record.keywords is None
            assert record.target_episode == 8


async def test_add_positional_arguments_still_work():
    """A-T3: 既存の位置引数4つ（および scope/ target まで）呼び出しが壊れないこと。

    `keywords` を**末尾のキーワード引数**として追加したため、
    従来の位置引数呼び出しは 1 文字も変えず通る。
    """
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)

            # 従来どおりの位置引数4つ
            r1 = await repo.add(1, "位置引数4つ", "説明", 4)
            # 位置引数6つ（scope まで）
            from src.models.foreshadowing_status import ForeshadowingScope

            r2 = await repo.add(1, "位置引数6つ", "説明", 5, 12, ForeshadowingScope.LONG_TERM)
            await repo.commit()

            assert r1.book_id == 1
            assert r1.title == "位置引数4つ"
            assert r1.planted_episode == 4
            assert r1.target_episode is None
            assert r1.keywords is None
            assert r1.status == "planted"

            assert r2.target_episode == 12
            assert r2.scope == ForeshadowingScope.LONG_TERM.value
            assert r2.keywords is None


async def test_add_many_calls_report_planted_per_row(monkeypatch):
    """A-T8: `add_many()` が `add()` と同じ `_report_planted` を1行ずつ呼ぶ。

    bulk 経路で設置メトリクスが脱落すると「設置件数」が本数だけ減るため、
    件数を固定する。
    """
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)

            reported: list = []

            async def _fake_report(record):
                reported.append(record.title)

            monkeypatch.setattr(repo, "_report_planted", _fake_report)

            rows = [
                {
                    "book_id": 1,
                    "title": f"一括{i}",
                    "description": "説明",
                    "planted_episode": 10 + i,
                    "target_episode": 20 + i,
                    "keywords": ["a,b", "c"],
                }
                for i in range(3)
            ]
            records = await repo.add_many(rows)
            await repo.commit()

            assert len(records) == 3
            assert reported == ["一括0", "一括1", "一括2"]
            for record in records:
                assert decode_keywords(record.keywords) == ["a,b", "c"]


async def test_add_many_without_keywords_reports_kpi(monkeypatch):
    """A-T8(補足): `keywords` 無しの一括でも KPI は脱落しない。"""
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            reported: list = []

            async def _fake_report(record):
                reported.append(record.id)

            monkeypatch.setattr(repo, "_report_planted", _fake_report)
            await repo.add_many(
                [
                    {"book_id": 1, "title": "T1", "description": "d", "planted_episode": 1},
                    {"book_id": 1, "title": "T2", "description": "d", "planted_episode": 2},
                ]
            )
            await repo.commit()
            assert len(reported) == 2


async def test_add_many_empty_rows_is_noop():
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.add_many([]) == []
            assert await repo.get_by_book_id(1) == []


async def test_add_many_rejects_bad_rows():
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            with pytest.raises(ValueError, match="book_id"):
                await repo.add_many(
                    [{"title": "T", "description": "d", "planted_episode": 1}]
                )
            with pytest.raises(ValueError, match="unexpected keys"):
                await repo.add_many(
                    [
                        {
                            "book_id": 1,
                            "title": "T",
                            "description": "d",
                            "planted_episode": 1,
                            "bogus": 1,
                        }
                    ]
                )


async def test_set_keywords_helper_roundtrip():
    """`ForeshadowingModel.set_keywords` / `keyword_list` の往復。"""
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            record = await repo.add(
                book_id=1, title="helper", description="d", planted_episode=1
            )
            record.set_keywords(["x,y", "z"])
            await repo.commit()
            assert record.keyword_list == ["x,y", "z"]

            row = (await repo.get_by_book_id(1))[0]
            assert row.keyword_list == ["x,y", "z"]


async def test_keywords_column_is_text_and_nullable_in_db():
    """追加した列が実際に Text / NULL 許容であること。"""
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            await session.execute(text("SELECT keywords FROM foreshadowings"))
            result = await session.execute(
                text("PRAGMA table_info(foreshadowings)")
            )
            # PRAGMA table_info の列: (cid, name, type, notnull, dflt_value, pk)
            columns = {row[1]: (row[2], row[3]) for row in result.fetchall()}
            assert "keywords" in columns
            column_type, notnull = columns["keywords"]
            assert column_type.upper() == "TEXT"
            assert not int(notnull), "NULL 許容であること"


async def test_naive_comma_join_would_break_proof():
    """A-T1 の前提固定: `,` 区切りの naive join は往復できない（期待を固定する）。"""
    tricky = ["a,b", "c"]
    naive = ",".join(tricky).split(",")
    assert decode_keywords(encode_keywords(tricky)) == tricky
    assert naive != tricky


# ── A-T9: マイグレーション整合 ───────────────────────

_MIGRATION_MODULE = "src.backend.alembic.versions.0035_add_foreshadowing_keywords"
_REPO_ROOT = Path(__file__).resolve().parents[3]

#: `books` の最小スタブ。`batch_alter_table` がテーブルをリフレクションする
#: 際に `books` を参照するため必要（0029 が作るテーブル群を模す）。
_BOOKS_DDL = """
CREATE TABLE books (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(200) NOT NULL
)
"""

#: 0035 が無い時代の foreshadowings テーブル定義（0029 と同一）。
_LEGACY_DDL = """
CREATE TABLE foreshadowings (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    title VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    planted_episode INTEGER NOT NULL,
    target_episode INTEGER,
    resolved_episode INTEGER,
    scope VARCHAR(32) NOT NULL DEFAULT 'short_term',
    status VARCHAR(20) NOT NULL DEFAULT 'planted',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE
)
"""


def _migration():
    import importlib

    return importlib.import_module(_MIGRATION_MODULE)


def test_migration_revisions_are_wired():
    """0035 が 0034 の直後に続いていること（実測した HEAD）。"""
    mod = _migration()
    assert mod.revision == "0035_add_foreshadowing_keywords"
    assert mod.down_revision == "0034_tasks_user_id"


def test_0035_is_the_only_head():
    """`heads` が2本以上だと `alembic upgrade head` が失敗する（分岐の回帰防止）。"""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["0035_add_foreshadowing_keywords"]


@pytest.fixture
def legacy_db(tmp_path):
    """`keywords` 列が無い旧スキーマの SQLite DB を作る。"""
    from sqlalchemy import create_engine

    path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.exec_driver_sql(_BOOKS_DDL)
        conn.exec_driver_sql(_LEGACY_DDL)
        conn.exec_driver_sql(
            "INSERT INTO books (id, title) VALUES (1, '既存作品')"
        )
        conn.exec_driver_sql(
            "INSERT INTO foreshadowings "
            "(book_id, title, description, planted_episode) VALUES (1, '既存', '既存', 1)"
        )
    try:
        yield engine
    finally:
        engine.dispose()


def _columns(engine) -> list:
    from sqlalchemy import inspect

    return [c["name"] for c in inspect(engine).get_columns("foreshadowings")]


def test_upgrade_adds_keywords_to_existing_table(legacy_db):
    """A-T9: 既存テーブルへ `keywords` 列が追加されること。"""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mod = _migration()
    assert "keywords" not in _columns(legacy_db)

    with legacy_db.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()

    assert "keywords" in _columns(legacy_db)


def test_upgrade_preserves_existing_rows(legacy_db):
    """既存行は保持され、keywords は NULL（backfill しない）になること。"""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mod = _migration()
    with legacy_db.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        rows = conn.exec_driver_sql(
            "SELECT title, planted_episode, keywords FROM foreshadowings"
        ).fetchall()
    assert rows == [("既存", 1, None)]


def test_upgrade_is_idempotent(legacy_db):
    """冪等: 2回呼んでも duplicate column で失敗しないこと。"""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mod = _migration()
    for _ in range(2):
        with legacy_db.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                mod.upgrade()
    assert _columns(legacy_db).count("keywords") == 1


def test_upgrade_is_noop_when_table_absent(tmp_path):
    """`foreshadowings` が無い環境では何もしない（0000 以前の DB で落ちない）。"""
    from sqlalchemy import create_engine, inspect

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mod = _migration()
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
    assert "foreshadowings" not in inspect(engine).get_table_names()
    engine.dispose()


def test_downgrade_drops_keywords(legacy_db):
    """downgrade も実装されていること。"""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mod = _migration()
    with legacy_db.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
    assert "keywords" in _columns(legacy_db)

    with legacy_db.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.downgrade()

    columns = _columns(legacy_db)
    assert "keywords" not in columns
    # 他のカラムは落とさない（0029 由来のスキーマを壊さない）
    for name in ("id", "book_id", "title", "scope", "status"):
        assert name in columns


def test_downgrade_then_upgrade_roundtrip(legacy_db):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mod = _migration()
    with legacy_db.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.downgrade()  # 未適用なので no-op のはず
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        with Operations.context(MigrationContext.configure(conn)):
            mod.downgrade()
    assert "keywords" not in _columns(legacy_db)


def test_metadata_matches_migrated_schema(legacy_db):
    """A-T9: `Base.metadata` とマイグレーション結果の乖離を検出する。

    ORM が `keywords` を定義しているのにマイグレーションが空振り 하면
    本番で `no such column: keywords` になる。列集合を比較して固定する。
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect

    mod = _migration()
    with legacy_db.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()

    migrated_engine = create_engine(f"sqlite:///{legacy_db.url.database}")
    migrated_columns = {c["name"] for c in inspect(migrated_engine).get_columns("foreshadowings")}
    migrated_engine.dispose()

    metadata_columns = set(ForeshadowingModel.__table__.columns.keys())
    assert metadata_columns == migrated_columns, (
        "ORM とマイグレーションの列が不一致。"
        f" 差分: {sorted(metadata_columns ^ migrated_columns)}"
    )
