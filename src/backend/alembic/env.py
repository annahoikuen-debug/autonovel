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

        # `disable_existing_loggers=False` を明示する。
        #
        # `logging.config.fileConfig` の `disable_existing_loggers` 既定は **True** で、
        # この呼び出し時点までに生成済みのロガーすべてに `disabled=True` が焼き付く。
        # 結果としてアプリ本体のログ（`src.*` の各モジュール）が無言で消える。
        #
        # 2026-10-04 の公開前調査でこれが実際に観測された:
        #   1. `TestClient(app)` の lifespan が `init_db()` → `_run_alembic_upgrade()`
        #      → この fileConfig を呼ぶ
        #   2. 同時にそれまでに生成済みのロガー（実測 500 個）が 一括で disable される
        #   3. `caplog.at_level(...)` は level だけを下げ `disabled` は解除しないため、
        #      以降のログ依存テストが無言で失敗する（順序依存）
        #
        # Alembic 用の設定を読み込みたいだけで、既存アプリケーションのロガーを
        # 無効化する意図はないため、明示的に False を渡す。
        logging.config.fileConfig(
            config.config_file_name, disable_existing_loggers=False
        )

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,  # SQLite compatibility
        )

        with context.begin_transaction():
            context.run_migrations()


if config is not None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
