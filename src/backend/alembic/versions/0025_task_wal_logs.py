"""create task_wal_logs table

Revision ID: 0025_task_wal_logs
Revises: 0024_cost_consumption_logs

Phase 3 Part 5: Task Write-Ahead Log for crash recovery.
Stores execution state, input/output parameters, and heartbeats for each DAG task node.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_task_wal_logs"
down_revision = "0024_cost_consumption_logs"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists("task_wal_logs"):
        return

    op.create_table(
        "task_wal_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("dag_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=True),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_task_wal_logs_dag_id"),
        "task_wal_logs",
        ["dag_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_wal_logs_node_id"),
        "task_wal_logs",
        ["node_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_wal_logs_task_id"),
        "task_wal_logs",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_wal_logs_heartbeat"),
        "task_wal_logs",
        ["heartbeat_at"],
        unique=False,
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in inspector.get_indexes(table_name))


def downgrade() -> None:
    if _table_exists("task_wal_logs"):
        # create_all 由来の idx_* と本リビジョンの ix_* が混在し得るため、
        # 実在する index だけを落とす（冪等）。
        for index_name in (
            op.f("ix_task_wal_logs_heartbeat"),
            op.f("ix_task_wal_logs_task_id"),
            op.f("ix_task_wal_logs_node_id"),
            op.f("ix_task_wal_logs_dag_id"),
        ):
            if _index_exists("task_wal_logs", index_name):
                op.drop_index(index_name, table_name="task_wal_logs")
        op.drop_table("task_wal_logs")
