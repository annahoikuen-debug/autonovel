"""Step 20: API 4箇所の統合が完了し、全 import 経路が動作することを確認する。

API 層が分散していた4箇所（src/api/, src/backend/api/, src/backend/routers/,
src/interfaces/api/）を統合し、全経路が正しく動作することを検証する。

PLAN_Q3 完了により旧パス shim（src.api.* / src.backend.api.* / src.infrastructure.api.*）
は全削除し、shim registry は 0 件に到達済み。本テストは新パスのみを検証する。
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: 新パス（統合後）の import 経路 (module_path, expected_symbols)
API_IMPORT_PATHS = [
    ("src.backend.routers.dashboard", ["router"]),
    ("src.backend.routers.conflicts", ["router"]),
    ("src.backend.routers.agent_memory", ["router"]),
    ("src.backend.routers.admin_phase2", ["router", "enrichment_router", "rag_router"]),
    ("src.interfaces.api.app_factory", ["create_app", "build_lifespan"]),
    ("src.interfaces.api.styles", ["router"]),
    ("src.interfaces.api.platform_export", ["router"]),
    ("src.interfaces.api.metrics", []),
    ("src.infrastructure.external.api_client", []),
]


@pytest.mark.parametrize("module_path,symbols", API_IMPORT_PATHS)
def test_all_api_import_paths(module_path, symbols):
    """全ての API import 経路が動作する。"""
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        pytest.fail(f"{module_path} の import に失敗: {exc}")
    for symbol in symbols:
        assert hasattr(mod, symbol), \
            f"{module_path} に {symbol} が公開されていない"


def test_no_orphan_api_files():
    """移動元に実体ファイルが残っていない（旧パス shim は削除済み）。"""
    orphan_checks = [
        (ROOT / "src" / "api", ["dashboard.py", "conflicts.py", "agent_memory.py", "health.py"]),
        (ROOT / "src" / "backend" / "api", ["admin_phase2.py"]),
    ]
    for dir_path, removed_files in orphan_checks:
        for fname in removed_files:
            assert not (dir_path / fname).exists(), \
                f"{dir_path / fname} が残っている（PLAN_Q3 で削除済みであるべき）"


def test_wiring_imports_new_path():
    """wiring.py が新パス（src.backend.routers.admin_phase2）を import する。"""
    content = (ROOT / "src/backend/wiring.py").read_text(encoding="utf-8")
    assert "src.backend.routers.admin_phase2" in content, \
        "wiring.py が新パスを import していない"


def test_ruff_clean_api():
    """src/backend/routers/, src/interfaces/api/ が ruff check を通る。"""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src/backend/routers", "src/interfaces/api"],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
    )
    assert result.returncode == 0, \
        f"ruff check 失敗:\n{result.stdout}\n{result.stderr}"
