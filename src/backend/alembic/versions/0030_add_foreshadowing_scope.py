"""foreshadowings.scope カラムを確実に存在する状態にする（冪等）

Revision ID: 0030_add_foreshadowing_scope
Revises: 0029_foreshadowing_relations
Create Date: 2026-09-19 00:00:00.000000

注意（履歴）:
    本リビジョンは当初 `foreshadowings.scope` を無条件に `add_column` していたが、
    直前の 0029_foreshadowing_relations の ``create_table`` 内で既に同名の
    ``scope`` カラムを定義していた（0029 の 30 行目）。そのため新規DBでチェーンを
    最後まで通すと duplicate column で失敗し、0029 以前で止まった既存DBは 0030 が
    未適用という中途半端な状態になっていた。

    本リビジョンは「カラムが存在すれば何もしない、存在しなければ追加する」という
    冪等な挙動に変更し、どちらの起始点のDBでも正しく 0030 に到達できるようにする。
    0030 は実質的なスキーマ変更を持たないため、downgrade でも他のリビジョンが
    定義したカラムを落とさない。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0030_add_foreshadowing_scope'
down_revision = '0029_foreshadowing_relations'
branch_labels = None
depends_on = None

_TABLE = 'foreshadowings'
_COLUMN = 'scope'


def _column_exists() -> bool:
    """foreshadowings テーブルに scope カラムが既にあるか."""
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return False
    return any(col['name'] == _COLUMN for col in inspector.get_columns(_TABLE))


def upgrade() -> None:
    # 冪等化: 0029 が既に定義済なら追加しない（重複カラムエラーで失敗させない）
    if _column_exists():
        return
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.String(length=32), nullable=False, server_default='short_term'),
    )


def downgrade() -> None:
    # 本リビジョンは 0029 が定義したカラムを再確認しただけなので、
    # そのまま drop すると 0029 に依存するスキーマを壊す。安全のため何もしない。
    return
