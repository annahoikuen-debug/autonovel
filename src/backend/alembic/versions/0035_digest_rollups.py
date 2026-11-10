"""digest_rollups テーブルを作成（階層的逐次要約メモリのロールアップデータソース）

Revision ID: 0035_digest_rollups
Revises: 0034_tasks_user_id
Create Date: 2026-11-10 00:00:00.000000

背景（PLAN_M1 Phase 1 Step 4）:
    `digest_rollups` は 3層ローリング記憶を超える「巻>章>話」の
    ツリー状逐次要約を保存するテーブル。
    - level='block': 章（ブロック）の確定事実要約（デフォルト10話/章）
    - level='volume': 巻の確定事実要約（デフォルト5章/巻=50話/巻）

    stale_at はメンバ digests 更新で失効フラグとして設定され、
    次回の digest 保存時に該当 rollup の再生成トリガとなる。

    0000_initial_migration は `Base.metadata.create_all` を呼ぶため、
    create_all 経由で既にテーブルが存在する環境がありうる。
    ガードを入れて冪等化する。
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0035_digest_rollups"
down_revision = "0034_tasks_user_id"
branch_labels = None
depends_on = None

_TABLE = "digest_rollups"


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("level", sa.Text(), nullable=False),
            sa.Column("start_ep", sa.Integer(), nullable=False),
            sa.Column("end_ep", sa.Integer(), nullable=False),
            sa.Column("digest_text", sa.Text(), nullable=False),
            sa.Column("stale_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "book_id",
                "level",
                "start_ep",
                "end_ep",
                name="uq_digest_rollups_book_level_range",
            ),
        )
    if not _index_exists(_TABLE, "ix_digest_rollups_book_level"):
        op.create_index("ix_digest_rollups_book_level", _TABLE, ["book_id", "level"])
    if not _index_exists(_TABLE, "ix_digest_rollups_stale_at"):
        op.create_index("ix_digest_rollups_stale_at", _TABLE, ["stale_at"])


def downgrade() -> None:
    if _table_exists(_TABLE):
        op.drop_table(_TABLE)
