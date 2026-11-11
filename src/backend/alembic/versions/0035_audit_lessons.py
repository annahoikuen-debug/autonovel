"""audit_lessons テーブルを追加する (H8 Phase E1: 教訓メモリ).

監査失敗教訓を作品単位で永続化し、Reflexion 型の改稿ループで
次話執筆プロンプトへ注入するためのテーブル。

方針:
* add-only（既存列・既存テーブルに触れない）。存在ガード付きで冪等。
* books への FK は ondelete="CASCADE"。
* status/index はクエリ頻度の高い (book_id, status, dimension) に配置。
* down_revision: 0035_digest_rollups (PLAN_M1) と 0034 から分岐していたため
  線形化した（複数 head による `alembic upgrade head` 失敗の解消）。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0035_audit_lessons"
down_revision = "0035_digest_rollups"
branch_labels = None
depends_on = None

_TABLE_NAME = "audit_lessons"


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _inspector().get_table_names()


def _index_exists(table: str, index_name: str) -> bool:
    insp = _inspector()
    if table not in insp.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in insp.get_indexes(table))


def upgrade() -> None:
    if not _table_exists("books"):
        # books テーブルが無い環境では FK を貼れないためスキップ。
        return

    if not _table_exists(_TABLE_NAME):
        op.create_table(
            _TABLE_NAME,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "book_id",
                sa.Integer(),
                sa.ForeignKey("books.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("episode_num", sa.Integer(), nullable=False, index=True),
            sa.Column("dimension", sa.String(length=64), nullable=False, index=True),
            sa.Column("lesson_text", sa.Text(), nullable=False),
            sa.Column("severity", sa.String(length=16), nullable=False, default="medium"),
            sa.Column("occurrences", sa.Integer(), nullable=False, default=1),
            sa.Column("status", sa.String(length=16), nullable=False, default="active", index=True),
            sa.Column("first_seen_episode", sa.Integer(), nullable=False),
            sa.Column("last_seen_episode", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if not _index_exists(_TABLE_NAME, "ix_audit_lessons_book_status_dim"):
        op.create_index(
            "ix_audit_lessons_book_status_dim",
            _TABLE_NAME,
            ["book_id", "status", "dimension"],
        )


def downgrade() -> None:
    if _table_exists(_TABLE_NAME):
        op.drop_table(_TABLE_NAME)
