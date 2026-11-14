"""task_wal_logs に worker_id カラムを追加

マルチワーカー構成で、自分のタスクと他ワーカーのタスクを区別するため、
task_wal_logs に worker_id カラムを追加する（Step 51-53, H12）。

Revision ID: 0036_task_wal_logs_worker_id
Revises: 0035_audit_lessons
Create Date: 2026-11-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0036_task_wal_logs_worker_id"
down_revision = "0035_audit_lessons"
branch_labels = None
depends_on = None


def upgrade():
    """task_wal_logs に worker_id カラムを追加。

    0000_initial_migration が Base.metadata.create_all() で ORM 定義のテーブルを
    先行作成するため、カラムが既に存在するケースを冪等に扱う（H12）。
    """
    insp = sa.inspect(op.get_bind())
    existing_cols = {col["name"] for col in insp.get_columns("task_wal_logs")}
    if "worker_id" not in existing_cols:
        op.add_column("task_wal_logs", sa.Column("worker_id", sa.String(length=64), nullable=True))


def downgrade():
    insp = sa.inspect(op.get_bind())
    existing_cols = {col["name"] for col in insp.get_columns("task_wal_logs")}
    if "worker_id" in existing_cols:
        op.drop_column("task_wal_logs", "worker_id")
