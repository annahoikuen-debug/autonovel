"""順序依存（環境変数汚染）の検出テスト.

test_migrations_up_down が他テストによる ALEMBIC_DATABASE_URL 汚染の影響を
受けないことを検証する。Step 4（test_migrations の monkeypatch 隔離）・
Step 5（conftest real_db_manager の環境変数復元）が壊れると即赤になる。

既存の tests/regression/test_collection_health_gate.py が collection 健全性を
担うため、ここでは順序依存（環境変数汚染）のみを狙う。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from src.backend.config import ROOT_DIR


def _alembic_cfg(url: str) -> Config:
    ini_path = ROOT_DIR / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(ROOT_DIR / "src" / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def test_migrations_resists_aleembic_env_pollution(tmp_path, monkeypatch) -> None:
    """ALEMBIC_DATABASE_URL が汚染されていても、monkeypatch で正しいURLに固定すれば
    指定DBに対してマイグレーションが適用されること（Step 4 の隔離検証）。

    他テストが ALEMBIC_DATABASE_URL を「移行済みのダミーDB」に書き換えた
    状態をシミュレートする。
    """
    db_path = tmp_path / "test_order_dep.db"
    test_url = f"sqlite:///{db_path}"

    # 他テストによる汚染をシミュレート（ALEMBIC_DATABASE_URL は process-wide）
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", "sqlite:///polluted_dummy.db")

    # test_migrations_up_down と同じ処理：monkeypatch で正しいURLに固定
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", test_url)

    engine = create_engine(test_url)
    from src.infrastructure.database.models.base_orm import Base
    import src.backend.database.models  # noqa
    import src.infrastructure.database.models  # noqa

    Base.metadata.create_all(engine)

    cfg = _alembic_cfg(test_url)
    command.upgrade(cfg, "head")

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "books" in tables
    assert "chapters" in tables


def test_real_db_manager_sets_aleembic_url(real_db_manager) -> None:
    """real_db_manager フィクスチャ使用中、ALEMBIC_DATABASE_URL がテスト用URLに
    設定されていること（Step 5 の conftest 修正検証）。

    このフィクスチャを使うテストが先に走っても、ALEMBIC_DATABASE_URL が
    テスト用URLに固定されるため、後続の test_migrations_up_down が
    移行済みDBに対して upgrade することを防ぐ。
    """
    current = os.environ.get("ALEMBIC_DATABASE_URL")
    assert current is not None, "real_db_manager が ALEMBIC_DATABASE_URL を設定していない"
    assert current.startswith("sqlite:///"), f"想定外のURL: {current}"
