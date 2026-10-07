"""スキーマとモデルの乖離を是正する (billing / plots / relations / indexes / tenant)。

Revision ID: 0033_schema_reconciliation
Revises: 0032_tenant_user_fk
Create Date: 2026-10-02 00:00:00.000000

本リビジョンは以下の実在するドリフトを、**既にマイグレーション済みの DB も
含めて**是正する（履歴リビジョン 0028 の書き換えはしない）。

1. ``stripe_webhook_events``: 0028 が作る DDL とモデルの
   ``StripeWebhookEvent``（``event_id`` PK / ``status`` / ``processed_at``）が
   食い違っていた。``billing_webhook.py:80`` の ``db.get(StripeWebhookEvent, event_id)``
   は存在しない列の PK 参照で必ず ``OperationalError`` になる。テーブルを
   モデル定義どおりに再構築し、``stripe_event_id`` を ``event_id`` へ、
   ``processed`` を ``status`` へ移行する。
2. ``credit_transactions.created_at`` / ``stripe_webhook_events.created_at`` の
   server default が 0028 で ``sa.text('now()')`` になっており、SQLite に存在
   しない ``now()`` 関数が CREATE 時の既定値として焼き込まれ、以降の
   **全 INSERT が失敗**していた。``CURRENT_TIMESTAMP``（= ``sa.func.now()``）に
   再構築して直す（SQLite のみ。PostgreSQL の ``now()`` は実在関数なので無害）。
3. ``plots``: ``is_plot_twist`` / ``candidates`` がモデルに存在しなかったため
   ``create_or_replace_plot`` の代入が SQLAlchemy により黙って捨てられていた。
4. ``character_relations``: ``description`` 列と一意制約が欠落。
5. ``episode_digests``: ``(book_id, episode_num)`` の重複行を整理し、
   一意インデックス ``uq_episode_digests_book_episode`` を追加する。
6. ``users.tenant_id`` と ``chk_user_credits_non_negative`` を追加
   （0027 は users テーブルを既存環境向けに作る際に新カラムを一切追加していない）。
7. hot filter 列（``books.tenant_id`` / ``books.version`` / ``chapters.branch_id`` /
   ``plots.branch_id`` / ``audit_issues.book_id`` / ``bibles.book_id``）の index。
8. ``0027`` が ``idx_<table>_user_id``、``create_all`` が ``ix_<table>_user_id`` を
同じ列に二重に張っている。**同一列の冗長 index** なので片方は落とせるが、
   ``ix_`` 側が実在するときだけ ``idx_`` 側を落とす（``idx_`` しか無い環境では
   唯一の index なので消さない）。

SQLite の ``PRAGMA foreign_keys`` は ``env.py`` で設定されていない（既定 OFF）だが、
DatabaseManager 側は ON で動かすため、``users`` のような**外部キー親テーブルを
batch_alter_table で再構築する時は**明示的に OFF にして外す。OFF の間は
子テーブルの REFERENCES を検証しないので、batch 再構築による
「子行が孤立する / FOREIGN KEY constraint failed で落ちる」事故を防ぐ。
"""
from __future__ import annotations

from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0033_schema_reconciliation"
down_revision = "0032_tenant_user_fk"
branch_labels = None
depends_on = None


def _bind():
    return op.get_bind()


def _dialect_name() -> str:
    return _bind().dialect.name


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in inspector.get_indexes(table_name))


def _unique_exists(table_name: str, column_names: tuple[str, ...]) -> bool:
    inspector = sa.inspect(_bind())
    if table_name not in inspector.get_table_names():
        return False
    for uq in inspector.get_unique_constraints(table_name):
        if tuple(uq.get("column_names") or ()) == column_names:
            return True
    for ix in inspector.get_indexes(table_name):
        if ix.get("unique") and tuple(ix.get("column_names") or ()) == column_names:
            return True
    return False


def _safe_bool_default() -> str:
    return "false" if _dialect_name() == "postgresql" else "0"


@contextmanager
def _sqlite_foreign_keys_off():
    """SQLite のテーブル再構築中だけ外部キー検証を止める。

    ``PRAGMA foreign_keys`` はトランザクション内では変更できない no-op だが、
    Alembic の batch モードは DDL のみ（pysqlite は DDL で暗黙トランザクションを
    開始しない）なので実際には効く。PostgreSQL では何もしない。
    """
    bind = _bind()
    if bind.dialect.name != "sqlite":
        yield
        return
    bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        yield
    finally:
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")


def _rebuild_table(old: str, new: str, columns: list, select_expr: str) -> None:
    """``old`` を ``columns`` 定义的テーブルに置き換えて ``old`` の行を複写する。

    ``select_expr`` は複写元から新テーブルへの SELECT 文（列名を新テーブル順に揃える）。
    SQLite / PostgreSQL の両方で動く（``op.rename_table`` は両対応）。
    """
    op.create_table(new, *columns)
    # columns には制約 (PrimaryKeyConstraint / ForeignKeyConstraint) も含まれ得る。
    # 制約オブジェクトの .name は None のため、実列のみ抽出する。
    col_names = [c.name for c in columns if isinstance(c, sa.Column) and c.name]
    op.execute(
        "INSERT INTO {new} ({cols}) {select_expr}".format(
            new=new,
            cols=", ".join(col_names),
            select_expr=select_expr,
        )
    )
    # 元テーブルに張 uniques があると DROP が制約違反で落ちるので先に落とす
    inspector = sa.inspect(_bind())
    for ix in inspector.get_indexes(old):
        if ix.get("unique"):
            op.drop_index(ix["name"], table_name=old)
    op.drop_table(old)
    op.rename_table(new, old)


# ==========================================
# 1 & 2. stripe_webhook_events
# ==========================================
def _fix_stripe_webhook_events() -> None:
    if not _table_exists("stripe_webhook_events"):
        return
    if _column_exists("stripe_webhook_events", "event_id"):
        # 既にモデル形（後続の partial 適用など）。server_default だけ整える。
        return

    _rebuild_table(
        "stripe_webhook_events",
        "stripe_webhook_events__0033",
        [
            sa.Column("event_id", sa.String(length=255), nullable=False),
            sa.Column("event_type", sa.String(length=100), nullable=False),
            sa.Column(
                "status",
                sa.String(length=30),
                nullable=False,
                server_default=sa.text("'processed'"),
            ),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.Column("processed_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("event_id"),
        ],
        # stripe_event_id → event_id、processed → status へ移行
        "SELECT stripe_event_id, "
        "SUBSTR(event_type, 1, 100), "
        "CASE WHEN processed THEN 'processed' ELSE 'processing' END, "
        "created_at, CURRENT_TIMESTAMP FROM stripe_webhook_events",
    )


# ==========================================
# 2. credit_transactions の server default
# ==========================================
def _fix_credit_transactions_default() -> None:
    """``sa.text('now()')`` は SQLite に存在しない関数で、INSERT が全滅する。

    PostgreSQL では ``now()`` が実在関数なので再構築不要（無害）。
    """
    if _dialect_name() != "sqlite":
        return
    if not _table_exists("credit_transactions"):
        return

    _rebuild_table(
        "credit_transactions",
        "credit_transactions__0033",
        [
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("balance_after", sa.Integer(), nullable=False),
            sa.Column("transaction_type", sa.String(length=30), nullable=False),
            sa.Column("task_id", sa.String(length=100), nullable=True),
            sa.Column("description", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        ],
        "SELECT id, user_id, amount, balance_after, transaction_type, task_id, "
        "description, COALESCE(created_at, CURRENT_TIMESTAMP) FROM credit_transactions",
    )
    for index_name, columns in (
        ("ix_credit_transactions_user_id", ["user_id"]),
        ("ix_credit_transactions_task_id", ["task_id"]),
    ):
        if not _index_exists("credit_transactions", index_name):
            op.create_index(index_name, "credit_transactions", columns)


# ==========================================
# 3. plots.is_plot_twist / plots.candidates
# ==========================================
def _add_plot_columns() -> None:
    if not _table_exists("plots"):
        return
    if not _column_exists("plots", "is_plot_twist"):
        op.add_column(
            "plots",
            sa.Column(
                "is_plot_twist",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text(_safe_bool_default()),
            ),
        )
    if not _column_exists("plots", "candidates"):
        op.add_column(
            "plots",
            sa.Column("candidates", sa.Text(), nullable=True, server_default=sa.text("'[]'")),
        )


# ==========================================
# 4. character_relations.description / 一意制約
# ==========================================
def _fix_character_relations() -> None:
    if not _table_exists("character_relations"):
        return
    if not _column_exists("character_relations", "description"):
        op.add_column("character_relations", sa.Column("description", sa.Text(), nullable=True))

    edge_cols = ("book_id", "source_char_id", "target_char_id", "relation_type")
    if _unique_exists("character_relations", edge_cols):
        return

    # 重複エッジを newest(id最大) 1 行に畳む。**この時点で重複分は失われる**
    # （同一エッジの古い行が削除される。哪儿 teknoloji.shadow 行の削除は不可避）。
    op.execute(
        "DELETE FROM character_relations WHERE id NOT IN ("
        "SELECT MAX(id) FROM character_relations "
        "GROUP BY book_id, source_char_id, target_char_id, relation_type)"
    )
    with _sqlite_foreign_keys_off():
        with op.batch_alter_table("character_relations") as batch:
            batch.create_unique_constraint("uq_character_relations_edge", list(edge_cols))


# ==========================================
# 5. episode_digests の (book_id, episode_num) 一意化
# ==========================================
def _fix_episode_digests_unique() -> None:
    if not _table_exists("episode_digests"):
        return
    if _unique_exists("episode_digests", ("book_id", "episode_num")):
        return

    # 同一話に複数のダイジェスト行がある環境（再試行の残骸）は id 最大のみ残す。
    # **残りの行は削除され、データが失われる**（新しい方=再試行の結果を残す）。
    op.execute(
        "DELETE FROM episode_digests WHERE id NOT IN ("
        "SELECT MAX(id) FROM episode_digests GROUP BY book_id, episode_num)"
    )
    with _sqlite_foreign_keys_off():
        op.create_index(
            "uq_episode_digests_book_episode",
            "episode_digests",
            ["book_id", "episode_num"],
            unique=True,
        )


# ==========================================
# 6. users.tenant_id / chk_user_credits_non_negative
# ==========================================
def _fix_users_tenant_and_check() -> None:
    if not _table_exists("users"):
        return
    if not _column_exists("users", "tenant_id"):
        op.add_column("users", sa.Column("tenant_id", sa.Integer(), nullable=True))
    if not _index_exists("users", "ix_users_tenant_id"):
        op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    inspector = sa.inspect(_bind())
    has_check = any(
        (c.get("name") or "") == "chk_user_credits_non_negative"
        for c in inspector.get_check_constraints("users")
    )
    if has_check:
        return

    # users は books / branches / chapters などの外部キー親なので再構築中は
    # PRAGMA foreign_keys を OFF にして、子行を巻き込まないようにする。
    with _sqlite_foreign_keys_off():
        with op.batch_alter_table("users") as batch:
            batch.create_check_constraint("chk_user_credits_non_negative", "credits >= 0")


# ==========================================
# 7 & 8. 冗長 index と hot filter index
# ==========================================
_HOT_INDEXES = (
    ("books", "ix_books_tenant_id", ["tenant_id"]),
    ("chapters", "ix_chapters_branch_id", ["branch_id"]),
    ("plots", "ix_plots_branch_id", ["branch_id"]),
    ("audit_issues", "ix_audit_issues_book_id", ["book_id"]),
    ("bibles", "ix_bibles_book_id", ["book_id"]),
)


def _add_hot_indexes() -> None:
    for table, index_name, columns in _HOT_INDEXES:
        if not _table_exists(table):
            continue
        if _index_exists(table, index_name):
            continue
        op.create_index(index_name, table, columns)


def _add_books_version() -> None:
    """``update_book_cumulative_tension`` の楽観ロック用カラム。"""
    if not _table_exists("books"):
        return
    if not _column_exists("books", "version"):
        op.add_column(
            "books",
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        )


def _drop_redundant_user_id_indexes() -> None:
    """``idx_<table>_user_id`` (0027) と ``ix_<table>_user_id`` (create_all) の重複除去。

    ``ix_`` 側が**実在するときだけ** ``idx_`` 側を落とす。``idx_`` しか無い環境では
    唯一の index になるため落とさない。
    """
    for table in ("books", "branches", "chapters"):
        if not _table_exists(table):
            continue
        if _index_exists(table, f"ix_{table}_user_id") and _index_exists(table, f"idx_{table}_user_id"):
            op.drop_index(f"idx_{table}_user_id", table_name=table)


def upgrade() -> None:
    _fix_stripe_webhook_events()
    _fix_credit_transactions_default()
    _add_plot_columns()
    _fix_character_relations()
    _fix_episode_digests_unique()
    _fix_users_tenant_and_check()
    _add_books_version()
    _add_hot_indexes()
    _drop_redundant_user_id_indexes()


def downgrade() -> None:
    if _table_exists("books") and _index_exists("books", "ix_books_tenant_id"):
        op.drop_index("ix_books_tenant_id", table_name="books")
    if _table_exists("books") and _column_exists("books", "version"):
        with _sqlite_foreign_keys_off():
            with op.batch_alter_table("books") as batch:
                batch.drop_column("version")
    if _table_exists("bibles") and _index_exists("bibles", "ix_bibles_book_id"):
        op.drop_index("ix_bibles_book_id", table_name="bibles")
    if _table_exists("audit_issues") and _index_exists("audit_issues", "ix_audit_issues_book_id"):
        op.drop_index("ix_audit_issues_book_id", table_name="audit_issues")
    if _table_exists("plots") and _index_exists("plots", "ix_plots_branch_id"):
        op.drop_index("ix_plots_branch_id", table_name="plots")
    if _table_exists("chapters") and _index_exists("chapters", "ix_chapters_branch_id"):
        op.drop_index("ix_chapters_branch_id", table_name="chapters")

    if _table_exists("episode_digests") and _index_exists(
        "episode_digests", "uq_episode_digests_book_episode"
    ):
        op.drop_index("uq_episode_digests_book_episode", table_name="episode_digests")

    if _table_exists("character_relations"):
        inspector = sa.inspect(_bind())
        for uq in inspector.get_unique_constraints("character_relations"):
            if uq.get("name") == "uq_character_relations_edge":
                with _sqlite_foreign_keys_off():
                    with op.batch_alter_table("character_relations") as batch:
                        batch.drop_constraint("uq_character_relations_edge", type_="unique")
        if _column_exists("character_relations", "description"):
            with _sqlite_foreign_keys_off():
                with op.batch_alter_table("character_relations") as batch:
                    batch.drop_column("description")

    if _table_exists("plots"):
        for column in ("candidates", "is_plot_twist"):
            if _column_exists("plots", column):
                with _sqlite_foreign_keys_off():
                    with op.batch_alter_table("plots") as batch:
                        batch.drop_column(column)

    # users は新規実装なのでカラムは残す（drop すると books 等が孤立する）。
    # 0028 の元の形へ戻すにはstripe_webhook_events の再構築が不可逆なので行わない。
