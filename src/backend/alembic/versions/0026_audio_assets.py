"""0026_audio_assets.py

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_audio_assets"
down_revision = "0025_task_wal_logs"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in inspector.get_indexes(table_name))


def upgrade():
    # 0000_initial_migration は Base.metadata.create_all() で ORM 定義のテーブルを
    # 全て作成するベースラインmigrationのため、本テーブルは既に存在し得る。
    # 既存ガイド (0011 等) と同様に存在チェックで冪等化する。
    if not _table_exists("audio_assets"):
        op.create_table(
            "audio_assets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("book_id", sa.Integer(), sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("episode_num", sa.Integer(), nullable=False),
            sa.Column("file_path", sa.String(500), nullable=False),
            sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    if _table_exists("audio_assets") and not _index_exists("audio_assets", "idx_audio_assets_book_ep"):
        op.create_index("idx_audio_assets_book_ep", "audio_assets", ["book_id", "episode_num"])


def downgrade():
    if _table_exists("audio_assets") and _index_exists("audio_assets", "idx_audio_assets_book_ep"):
        op.drop_index("idx_audio_assets_book_ep", table_name="audio_assets")
    if _table_exists("audio_assets"):
        op.drop_table("audio_assets")
