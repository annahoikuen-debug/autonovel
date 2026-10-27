"""episode_digests テーブルを作成（3層ローリング記憶の Layer2 データソース）

Revision ID: 0031_episode_digests
Revises: 0030_add_foreshadowing_scope
Create Date: 2026-09-28 00:00:00.000000

背景（v5.3 長編耐性）:
    `EpisodeDigestModel`（episode_digests）は 3層ローリング記憶の Layer2
    「過去の確定事実ダイジェスト」のデータソースとして定義されていたが、
    DDL マイグレーションが存在せず、Alembic で構築したDBにはテーブルが
    存在しないままだった。加えて `EpisodeDigestService` の本番呼び出しが
    無かったため、Layer2 は `chapters.content[:100]` という生テキストの切り出し
    に依存していた。本リビジョンでテーブルを確実に存在する状態にする。

    なお 0000_initial_migration は `Base.metadata.create_all` を呼ぶため、
    create_all 経由で既にテーブルが存在する環境がありうる。0029 と同様に
    ガードを入れて冪等化する。"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0031_episode_digests'
down_revision = '0030_add_foreshadowing_scope'
branch_labels = None
depends_on = None

_TABLE = 'episode_digests'


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
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('book_id', sa.Integer(), nullable=False),
            sa.Column('episode_num', sa.Integer(), nullable=False),
            sa.Column('digest_text', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False,
                      server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False,
                      server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
        )
    if not _index_exists(_TABLE, 'ix_episode_digests_book_id'):
        op.create_index('ix_episode_digests_book_id', _TABLE, ['book_id'])
    if not _index_exists(_TABLE, 'ix_episode_digests_episode_num'):
        op.create_index('ix_episode_digests_episode_num', _TABLE, ['episode_num'])
    # Layer2 は (book_id, episode_num) で話数順に読み出す
    if not _index_exists(_TABLE, 'ix_episode_digests_book_episode'):
        op.create_index(
            'ix_episode_digests_book_episode', _TABLE, ['book_id', 'episode_num']
        )


def downgrade() -> None:
    if _table_exists(_TABLE):
        op.drop_table(_TABLE)
