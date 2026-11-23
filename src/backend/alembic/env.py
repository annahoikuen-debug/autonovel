from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# Add project root to path for model imports
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# Import models to register them with Base.metadata
from src.backend.database.models import Base  # noqa: E402

config = getattr(context, "config", None)

if config is not None:
    # Allow overriding database URL via environment variable
    database_url = os.environ.get("ALEMBIC_DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    config.set_main_option("sqlalchemy.url", database_url)

    # Interpret the config file for Python logging.
    if config.config_file_name is not None:
        import logging.config

        # disable_existing_loggers=False: 既定 (True) だとマイグレーション実行時に
        # アプリ側の既存ロガー (src.*) が無効化され、以降のログが消える。
        # プログラムから alembic を呼ぶサーバープロセスでもログを殺さないため明示。
        logging.config.fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _include_object(object, name, type_, reflected, compare_to):
    """alembic autogenerate/check の対象オブジェクトをフィルタリング。

    target_metadata（SQLAlchemy ORMモデル）に登録されていないが
    実際のDBに存在するテーブル（マイグレーションで生SQL作成されたテーブル等）
    を「removed」と誤検出しないよう、compare_to が None のテーブルをスキップする。

    対象:
    - digest_rollups, rag_reflection_history, audit_specialist_results:
      マイグレーションファイルで生SQL作成済み。ORMモデル未作成のため
      target_metadata に登録されていない。
    - uow_test: テスト用ワークテーブル。ORMモデル・マイグレーション両方未作成。
    """
    if type_ == "table" and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")  # type: ignore[union-attr]
    assert url is not None, "sqlalchemy.url must be set in alembic.ini"
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = config.get_main_option("sqlalchemy.url")  # type: ignore[union-attr]
    assert url is not None, "sqlalchemy.url must be set in alembic.ini"
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,  # SQLite compatibility
            include_object=_include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if config is not None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
