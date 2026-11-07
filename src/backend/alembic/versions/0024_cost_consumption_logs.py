"""create cost_consumption_logs table

Revision ID: 0024_cost_consumption_logs
Revises: 0021_publication_schedules
Branch labels: None
Depends on: None

Part 2: Token budget & API cost monitoring guard.
Records detailed token consumption per agent/model for cost analytics
and automatic model downgrade decisions.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_cost_consumption_logs"
down_revision = "0022_pdca_history"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()



def ix_exists(index_name: str, table_name: str) -> bool:
    """インデックスが実在する場合のみ True（create_all フォールバック DB 対策）。"""
    import sqlalchemy as sa

    insp = sa.inspect(op.get_bind())
    if table_name not in insp.get_table_names():
        return False
    return any(i["name"] == index_name for i in insp.get_indexes(table_name))

def upgrade() -> None:
    if _table_exists("cost_consumption_logs"):
        return

    op.create_table(
        "cost_consumption_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_id", sa.Integer(), sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=True),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cost_log_book_id"), "cost_consumption_logs", ["book_id"], unique=False)
    op.create_index(op.f("ix_cost_log_agent_name"), "cost_consumption_logs", ["agent_name"], unique=False)
    op.create_index(op.f("ix_cost_log_timestamp"), "cost_consumption_logs", ["timestamp"], unique=False)


def downgrade() -> None:
    if _table_exists("cost_consumption_logs"):
        if ix_exists("ix_cost_log_timestamp", "cost_consumption_logs"):
            op.drop_index("ix_cost_log_timestamp", table_name="cost_consumption_logs")
        if ix_exists("ix_cost_log_agent_name", "cost_consumption_logs"):
            op.drop_index("ix_cost_log_agent_name", table_name="cost_consumption_logs")
        if ix_exists("ix_cost_log_book_id", "cost_consumption_logs"):
            op.drop_index("ix_cost_log_book_id", table_name="cost_consumption_logs")
        op.drop_table("cost_consumption_logs")
