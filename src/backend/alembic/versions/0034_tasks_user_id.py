"""tasks に所有者カラム (user_id) を追加する。

Revision ID: 0034_tasks_user_id
Revises: 0033_schema_reconciliation
Create Date: 2026-10-02 00:00:00.000000

``Task`` (``src/infrastructure/database/models/task.py``) には所有者を示す列が無く、
``_assert_task_ownership`` (``src/backend/routers/tasks.py:26``) は
``data.get("user_id")`` が来なければ（管理者でなければ）必ず拒否するため、
通常ユーザは自分のタスクを参照/削除できなかった。本リビジョンで ``user_id`` を足す。

方針:
* **nullable**。既存行の所有者は DB 上から分からないので、**backfill しない**。
  適当に実ユーザーを割り当てると別人のタスクとして扱われる（拒否される方が安全）。
  既存行は ``user_id IS NULL`` のまま残り、fail-closed によりアクセス拒否される。
* 定義は ``Book.user_id`` (``src/backend/database/models.py:90``) に合わせる:
  ``Integer`` / ``FK users.id ON DELETE CASCADE`` / ``nullable=True`` / ``index=True``。
* ``users`` が無い環境（0027 未適用）では FK を付けられないため、カラムだけを足す。
* 全操作は存在ガード付き（冪等）。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0034_tasks_user_id"
down_revision = "0033_schema_reconciliation"
branch_labels = None
depends_on = None

_INDEX_NAME = "ix_tasks_user_id"
_CONSTRAINT_NAME = "fk_tasks_user_id_users"


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _inspector().get_table_names()


def _column_exists(table: str, column: str) -> bool:
    insp = _inspector()
    if table not in insp.get_table_names():
        return False
    return any(col["name"] == column for col in insp.get_columns(table))


def _index_exists(table: str, index_name: str) -> bool:
    insp = _inspector()
    if table not in insp.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in insp.get_indexes(table))


def _has_fk(table: str, column: str, referred: str) -> bool:
    insp = _inspector()
    if table not in insp.get_table_names():
        return False
    for fk in insp.get_foreign_keys(table):
        if column in (fk.get("constrained_columns") or ()) and referred in (
            fk.get("referred_table") or ""
        ):
            return True
    return False


def upgrade() -> None:
    if not _table_exists("tasks"):
        return
    if not _column_exists("tasks", "user_id"):
        # 既存行は所有者が不明なので NOT NULL 化も backfill もしない（NULL のままにする）。
        op.add_column("tasks", sa.Column("user_id", sa.Integer(), nullable=True))

    if _table_exists("users") and not _has_fk("tasks", "user_id", "users"):
        # tasks は users の子なので、親側のテーブル再構築はここでは行わない
        # （PRAGMA の扱いは 0033 の _sqlite_foreign_keys_off を参照）。
        with op.batch_alter_table("tasks") as batch:
            batch.create_foreign_key(
                _CONSTRAINT_NAME, "users", ["user_id"], ["id"], ondelete="CASCADE"
            )

    if not _index_exists("tasks", _INDEX_NAME):
        op.create_index(_INDEX_NAME, "tasks", ["user_id"])


def downgrade() -> None:
    if not _table_exists("tasks"):
        return
    if _index_exists("tasks", _INDEX_NAME):
        op.drop_index(_INDEX_NAME, table_name="tasks")
    if _has_fk("tasks", "user_id", "users"):
        with op.batch_alter_table("tasks") as batch:
            batch.drop_constraint(_CONSTRAINT_NAME, type_="foreignkey")
    if _column_exists("tasks", "user_id"):
        with op.batch_alter_table("tasks") as batch:
            batch.drop_column("user_id")
