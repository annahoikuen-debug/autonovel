"""W1 リグレッションテスト: DB ドライバが環境に導入されていること。

asyncpg (``postgresql+asyncpg://``) と psycopg (``postgresql+psycopg://``) は
SQLAlchemy の該当ダイアレクトがモジュール直下で import するため、欠けると
``test_backend_database_core.py`` が ModuleNotFoundError でまとめて失敗する。
本テストは「ドライバ未導入」を早期に検出するための環境ガードである。
"""
from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize("module_name", ["asyncpg", "psycopg"])
def test_db_driver_importable(module_name: str) -> None:
    """asyncpg / psycopg が import 可能であること（欠ければ即 fail）。"""
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        pytest.fail(
            f"DB ドライバ {module_name!r} が未導入です: {exc}\n"
            "pyproject.toml の依存宣言を確認のうえ pip install すること。"
        )
    assert module is not None
