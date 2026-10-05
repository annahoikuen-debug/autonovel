"""foreshadowings.keywords カラムを追加する（冪等）。

Revision ID: 0035_add_foreshadowing_keywords
Revises: 0034_tasks_user_id
Create Date: 2026-10-05 00:00:00.000000

``ForeshadowingModel`` (``src/backend/database/models_foreshadowing.py``) に
``keywords``（設置時に付ける手がかり語）を足す。

方針:
    * **Text / nullable**。既存行は NULL のまま（＝未設定）で backfill しない。
      回収判定・既存クエリは `keywords` を読まないため、既存挙動に影響しない。
    * JSON 配列カラム（JSONB / ARRAY）は **使わない**。既存の SQLite DB へ
      安全に追加できるよう、SQL の側でも Text だけを使う
      （`encode_keywords` が JSON 文字列を Text へ入れる）。
    * `downgrade` は列を落とすだけ。0029 が作ったテーブルや他カラムには触らない。
    * 全操作に存在ガード（冪等）。`foreshadowings` 自体が未作成の
      環境（0000 ベースライン前）では何もしない。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0035_add_foreshadowing_keywords"
down_revision = "0034_tasks_user_id"
branch_labels = None
depends_on = None

_TABLE = "foreshadowings"
_COLUMN = "keywords"


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _inspector().get_table_names()


def _column_exists(table: str, column: str) -> bool:
    insp = _inspector()
    if table not in insp.get_table_names():
        return False
    return any(col["name"] == column for col in insp.get_columns(table))


def upgrade() -> None:
    if not _table_exists(_TABLE):
        return
    if _column_exists(_TABLE, _COLUMN):
        # 0000 の Base.metadata.create_all が先にテーブルを作った環境では
        # 既に列がある。duplicate column で落とさない。
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    if not _table_exists(_TABLE):
        return
    if not _column_exists(_TABLE, _COLUMN):
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column(_COLUMN)
