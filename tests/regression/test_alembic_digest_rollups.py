"""digest_rollups マイグレーション (0035) の upgrade/downgrade 往復テスト (PLAN_M1 Step 4).

SQLite 一時ファイル DB で `alembic upgrade head` → `digest_rollups` テーブル作成を確認し、
`alembic downgrade 0034` → テーブル削除を確認する。
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from src.backend.config import ROOT_DIR


def _make_cfg(url: str) -> Config:
    ini_path = ROOT_DIR / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(ROOT_DIR / "src" / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def _tables(engine) -> set[str]:
    inspector = inspect(engine)
    return set(inspector.get_table_names())


def test_0035_upgrade_creates_digest_rollups(tmp_path):
    """upgrade head で digest_rollups テーブルが作成される。"""
    db_path = tmp_path / "test_0035.db"
    test_url = f"sqlite:///{db_path}"
    cfg = _make_cfg(test_url)

    command.upgrade(cfg, "0035_digest_rollups")

    engine = create_engine(test_url)
    tables = _tables(engine)
    assert "digest_rollups" in tables, f"digest_rollups not in {tables}"
    assert "books" in tables
    assert "episode_digests" in tables


def test_0035_downgrade_removes_digest_rollups(tmp_path):
    """downgrade 0034 で digest_rollups テーブルが削除される（episode_digests は残る）。"""
    db_path = tmp_path / "test_0035_downgrade.db"
    test_url = f"sqlite:///{db_path}"
    cfg = _make_cfg(test_url)

    command.upgrade(cfg, "0035_digest_rollups")
    command.downgrade(cfg, "0034")

    engine = create_engine(test_url)
    tables = _tables(engine)
    assert "digest_rollups" not in tables, f"digest_rollups still in {tables}"
    assert "books" in tables
    assert "episode_digests" in tables
