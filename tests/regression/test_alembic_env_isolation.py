"""ALEMBIC_DATABASE_URL 環境変数の隔離テスト.

プロセス全体を汚染しないよう、_run_alembic_upgrade は
環境変数を呼び出し前の値に戻すことを保証する。

これにより、他テストが alembic 実行後に残した
ALEMBIC_DATABASE_URL の副作用で「移行済みDB」に対して
upgrade が走り table ... already exists になるバグを防ぐ。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from src.backend.database.core import _run_alembic_upgrade


def _make_cfg(url: str) -> Config:
    from src.backend.config import ROOT_DIR

    ini_path = ROOT_DIR / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(ROOT_DIR / "src" / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def test_run_alembic_upgrade_restores_environment_variable(tmp_path) -> None:
    """_run_alembic_upgrade を呼び出した後、ALEMBIC_DATABASE_URL が元に戻ること."""
    db_path = tmp_path / "test_isolation.db"
    test_url = f"sqlite:///{db_path}"

    os.environ["ALEMBIC_DATABASE_URL"] = "sqlite:///dummy_polluted.db"

    try:
        _run_alembic_upgrade(test_url)
    finally:
        pass

    assert os.environ.get("ALEMBIC_DATABASE_URL") == "sqlite:///dummy_polluted.db"


def test_run_alembic_upgrade_removes_variable_when_absent_before(tmp_path) -> None:
    """呼び出し前に ALEMBIC_DATABASE_URL が未設定なら、呼び出し後も未設定に戻ること."""
    db_path = tmp_path / "test_isolation2.db"
    test_url = f"sqlite:///{db_path}"

    os.environ.pop("ALEMBIC_DATABASE_URL", None)

    try:
        _run_alembic_upgrade(test_url)
    finally:
        pass

    assert os.environ.get("ALEMBIC_DATABASE_URL") is None


def test_upgrade_applies_to_specified_url_not_polluted_env(tmp_path) -> None:
    """ALEMBIC_DATABASE_URL が汚染されていても、指定URLに対してupgradeが走ること."""
    db_path = tmp_path / "test_isolation3.db"
    test_url = f"sqlite:///{db_path}"

    os.environ["ALEMBIC_DATABASE_URL"] = "sqlite:///dummy_polluted.db"

    try:
        _run_alembic_upgrade(test_url)
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)

    # テスト対象DBにテーブルが作成されていること（汚染先のダミーDBではない）
    engine = create_engine(test_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "books" in tables
    assert "chapters" in tables
