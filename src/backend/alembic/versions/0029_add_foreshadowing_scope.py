"""create foreshadowings and character_relations tables

Revision ID: 0029_foreshadowing_relations
Revises: 0028_billing_and_credits
Create Date: 2026-09-17 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0029_foreshadowing_relations'
down_revision = '0028_billing_and_credits'
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in inspector.get_indexes(table_name))


def upgrade() -> None:
    # 0000 のベースライン (Base.metadata.create_all) が既にテーブルを作成している
    # 可能性があるため、既存ガイド (0011 等) と同じガードで冪等化する。
    if not _table_exists('foreshadowings'):
        # 伏線ステートマシンテーブル
        op.create_table(
            'foreshadowings',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('book_id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('planted_episode', sa.Integer(), nullable=False),
            sa.Column('target_episode', sa.Integer(), nullable=True),
            sa.Column('resolved_episode', sa.Integer(), nullable=True),
            sa.Column('scope', sa.String(length=32), nullable=False, server_default='short_term'),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='planted'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
        )
    if not _index_exists('foreshadowings', 'ix_foreshadowings_book_id'):
        op.create_index('ix_foreshadowings_book_id', 'foreshadowings', ['book_id'])
    if not _index_exists('foreshadowings', 'ix_foreshadowings_status'):
        op.create_index('ix_foreshadowings_status', 'foreshadowings', ['status'])
    # 複合インデックス: 特定作品の未回収伏線を高速取得
    if not _index_exists('foreshadowings', 'ix_foreshadowings_book_status'):
        op.create_index('ix_foreshadowings_book_status', 'foreshadowings', ['book_id', 'status'])

    # キャラクター関係テーブル（グラフDB Edgeのリレーショナル置換）
    if not _table_exists('character_relations'):
        op.create_table(
            'character_relations',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('book_id', sa.Integer(), nullable=False),
            sa.Column('source_char_id', sa.Integer(), nullable=False),
            sa.Column('target_char_id', sa.Integer(), nullable=False),
            sa.Column('relation_type', sa.String(length=50), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
    if not _index_exists('character_relations', 'ix_character_relations_book_id'):
        op.create_index('ix_character_relations_book_id', 'character_relations', ['book_id'])


def downgrade() -> None:
    if _table_exists('character_relations'):
        op.drop_table('character_relations')
    if _table_exists('foreshadowings'):
        op.drop_table('foreshadowings')
