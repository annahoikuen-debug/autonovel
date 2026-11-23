"""ORM モデルと Alembic マイグレーション後の DB スキーマ整合性を検証する回帰テスト。

H12（worker_id 列追加）などで「マイグレーションだけ追加して ORM モデルを更新し忘れる」
事故を構造的に防ぐため、以下の両方向を検出する:

* ORM モデルに列があるが DB に無い（マイグレーション未適用 / DB 側の列欠落）
* DB に列があるが ORM モデルに無い（ORM 側の列欠落 = worker_recovery.py 等の AttributeError リスク）

spawn 対応のため Alembic はサブプロセスで実行し、ALEMBIC_DATABASE_URL で一時 SQLite DB を指定する。
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

# ORM モデルを全て Base.metadata に登録するため import（alembic/env.py と同経路）
from src.backend.database.models import Base  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic_upgrade_head(db_url: str) -> None:
    """ALEMBIC_DATABASE_URL を指定して alembic upgrade head をサブプロセスで実行する。

    env.py は ALEMBIC_DATABASE_URL 環境変数を sqlalchemy.url より優先するため、
    サブプロセスの環境変数で一時 DB を確実に指定する。alembic.ini はカレント
    ディレクトリ (REPO_ROOT) から自動読み込みされる。
    """
    env = dict(os.environ)
    env["ALEMBIC_DATABASE_URL"] = db_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        raise AssertionError(
            f"alembic upgrade head failed (exit {result.returncode}):\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


def _orm_column_names() -> dict[str, set[str]]:
    """ORM モデルごとのテーブル名 → カラム名集合を返す。"""
    tables: dict[str, set[str]] = {}
    for table in Base.metadata.tables.values():
        tables[table.name] = {col.name for col in table.columns}
    return tables


def _db_column_names(db_path: str) -> dict[str, set[str]]:
    """実 DB のテーブル名 → カラム名集合を返す。"""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        table_names = [row[0] for row in cur.fetchall()]
        tables: dict[str, set[str]] = {}
        for name in table_names:
            if name == "alembic_version":
                continue
            cur.execute(f'PRAGMA table_info("{name}")')
            tables[name] = {row[1] for row in cur.fetchall()}
        return tables
    finally:
        conn.close()


# プリプロジェクトで既に drift しているテーブル群。
# このテストの目的は「worker_id のように、マイグレーションと ORM モデルの
# 列定義が乖離する新規 drift」を検出することであり、以下は移行 / 除外の
# 対象外として文書化済み。各項目には理由とフォローアップ担当事項を記す。
#
#   audit_runs:           ORM モデルは存在するが、対応する Alembic マイグレーションが無い。
#                         create_all 経由でしか作られず、マイグレーション管理への移行は未着手。
#   rag_reflection_history: マイグレーション 0020 で作成されるが ORM モデルは無い（raw SQL 専用）。
#   digest_rollups:       マイグレーション 0035_digest_rollups で作成されるが ORM モデルは無い。
#   audit_specialist_results: マイグレーション 0019 で作成されるが ORM モデルは無い。
KNOWN_TABLE_DRIFT: dict[str, str] = {
    "audit_runs": "ORM モデルあり・マイグレーションなし（移行未着手）",
    "rag_reflection_history": "マイグレーションあり・ORM モデルなし（raw SQL 専用）",
    "digest_rollups": "マイグレーションあり・ORM モデルなし（raw SQL 専用）",
    "audit_specialist_results": "マイグレーションあり・ORM モデルなし（raw SQL 専用）",
}


def test_model_migration_parity(tmp_path: Path) -> None:
    """マイグレーション適用後の DB スキーマと ORM モデル定義が一致すること。"""
    db_path = tmp_path / "test.db"
    # tmp_path ベースディレクトリは pytest セッション間で再利用されることがあるため、
    # 既存ファイルを事前削除してクリーンな状態でマイグレーションを適用する
    db_path.unlink(missing_ok=True)
    db_url = f"sqlite:///{db_path}"
    _alembic_upgrade_head(db_url)

    orm_tables = _orm_column_names()
    db_tables = _db_column_names(str(db_path))

    # テーブル名集合は、既知 drift を除いて一致している必要がある
    orm_only = set(orm_tables) - set(db_tables) - set(KNOWN_TABLE_DRIFT)
    db_only = set(db_tables) - set(orm_tables) - set(KNOWN_TABLE_DRIFT)
    assert not orm_only and not db_only, (
        f"テーブル名の不一致（既知 drift 除外後）: ORMのみ={orm_only}, DBのみ={db_only}"
    )

    for table_name in orm_tables:
        if table_name in KNOWN_TABLE_DRIFT:
            continue
        orm_cols = orm_tables[table_name]
        db_cols = db_tables[table_name]
        missing_in_db = orm_cols - db_cols
        missing_in_orm = db_cols - orm_cols
        assert not missing_in_db, f"テーブル '{table_name}' の以下の列が DB に存在しません: {missing_in_db}"
        assert not missing_in_orm, (
            f"テーブル '{table_name}' の以下の列が ORM モデルに定義されていません: {missing_in_orm}"
        )
