"""tenant user_id に外部キー制約を追加する (新規 DB のみ)。

``0027_multitenancy_users.py:64`` は ``user_id`` を ``sa.Column`` として追加しただけで
``ForeignKey("users.id")`` を持たなかった。既存 DB では SQLite の制約で
batch_alter_table が使えないため本マイグレーションは**新規 DB にのみ**適用される前提。
既存 DB の防衛はアプリ層の ``verify_book_ownership`` が担う (owner_guard.py:48)。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_tenant_user_fk"
down_revision = "0031_episode_digests"
branch_labels = None
depends_on = None

_TABLES = ("books", "branches", "chapters")


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_fk(table: str, column: str, ref: str) -> bool:
    insp = _inspector()
    if not insp.has_table(table):
        return False
    for fk in insp.get_foreign_keys(table):
        if column in fk.get("constrained_columns", []) and ref in fk.get("referred_table", ""):
            return True
    return False


def upgrade() -> None:
    # Explicit definition per table to ensure FK constraints
    for table in _TABLES:
        if not _table_exists(table) or _has_fk(table, "user_id", "users"):
            continue
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                f"fk_{table}_user_id_users",
                "users",
                ["user_id"],
                ["id"],
            )
    # fk_books_user_id_users, fk_branches_user_id_users, fk_chapters_user_id_users


def downgrade() -> None:
    for table in reversed(_TABLES):
        if not _table_exists(table) or not _has_fk(table, "user_id", "users"):
            continue
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_user_id_users", type_="foreignkey")
