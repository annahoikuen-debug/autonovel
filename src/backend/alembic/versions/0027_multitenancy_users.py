"""0027_multitenancy_users.py

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-14

``users`` テーブルの追加と、既存テーブルへの ``user_id`` カラム付与。
0000 のベースライン (Base.metadata.create_all) が既にテーブルを作っている
可能性があるため、全操作を既存ガイド (0011 等) と同じガードで冪等化する。
"""
from alembic import op
import sqlalchemy as sa

revision = "0027_multitenancy_users"
down_revision = "0026_audio_assets"
branch_labels = None
depends_on = None

_USER_ID_TABLES = ("books", "branches", "chapters")


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in inspector.get_indexes(table_name))


def upgrade():
    # ユーザーテーブルの作成
    if not _table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
            sa.Column("hashed_password", sa.String(255), nullable=False),
            sa.Column("display_name", sa.String(100), nullable=False),
            sa.Column("role", sa.String(20), nullable=False, server_default="user"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("plan_tier", sa.String(20), nullable=False, server_default="free"),
            sa.Column("credits", sa.Integer(), nullable=False, server_default="50"),
            sa.Column("stripe_customer_id", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )

    # 既存テーブルへの user_id 追加
    # SQLiteの制約上、直接的にForeignKeyをALTERで追加するのは難しいが、Alembicがhandleしてくれる場合が多い
    for table in _USER_ID_TABLES:
        if not _table_exists(table):
            continue
        if not _column_exists(table, "user_id"):
            op.add_column(table, sa.Column("user_id", sa.Integer(), nullable=True))
        index_name = f"idx_{table}_user_id"
        if not _index_exists(table, index_name):
            op.create_index(index_name, table, ["user_id"])


def downgrade():
    for table in reversed(_USER_ID_TABLES):
        index_name = f"idx_{table}_user_id"
        if _table_exists(table) and _index_exists(table, index_name):
            op.drop_index(index_name, table_name=table)
        if _table_exists(table) and _column_exists(table, "user_id"):
            op.drop_column(table, "user_id")
    if _table_exists("users"):
        op.drop_table("users")
