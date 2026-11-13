"""Step 20: API 4箇所の統合が完了し、全 import 経路が動作することを確認する。

API 層が分散していた4箇所（src/api/, src/backend/api/, src/backend/routers/,
src/interfaces/api/）を統合し、旧パスの shim も含めて全経路が
正しく動作することを検証する。
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: 全ての API 関連 import 経路 (module_path, expected_symbols)
API_IMPORT_PATHS = [
    # 新パス（統合後）
    ("src.backend.routers.dashboard", ["router"]),
    ("src.backend.routers.conflicts", ["router"]),
    ("src.backend.routers.agent_memory", ["router"]),
    ("src.backend.routers.admin_phase2", ["router", "enrichment_router", "rag_router"]),
    # 旧パス（shim、維持必須）
    ("src.api.dashboard", ["router"]),
    ("src.api.conflicts", ["router"]),
    ("src.api.agent_memory", ["router"]),
    ("src.api.health", ["router"]),
    ("src.backend.api.admin_phase2", ["router", "enrichment_router", "rag_router"]),
    # 正しいレイヤー（移動不要）
    ("src.interfaces.api.app_factory", ["create_app", "build_lifespan"]),
    ("src.interfaces.api.styles", ["router"]),
    ("src.interfaces.api.platform_export", ["router"]),
    ("src.interfaces.api.metrics", []),
    # 外部APIクライアント（Step 18 で移設）
    ("src.infrastructure.external.api_client", []),
    ("src.infrastructure.api.api_client", []),
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
    """移動元に不要な実体ファイルが残っていない。"""
    orphan_checks = [
        (ROOT / "src" / "api", ["dashboard.py", "conflicts.py", "agent_memory.py"]),
        (ROOT / "src" / "backend" / "api", ["admin_phase2.py"]),
    ]
    for dir_path, removed_files in orphan_checks:
        for fname in removed_files:
            path = dir_path / fname
            if path.exists():
                content = path.read_text(encoding="utf-8")
                assert "shim" in content.lower() or "後方互換" in content, \
                    f"{path} が shim ではなく実体ファイルとして残っている"


def test_wiring_imports_new_path():
    """wiring.py が新パス（src.backend.routers.admin_phase2）を import する。"""
    content = (ROOT / "src/backend/wiring.py").read_text(encoding="utf-8")
    assert "src.backend.routers.admin_phase2" in content, \
        "wiring.py が新パスを import していない"
    assert "src.backend.api.admin_phase2" not in content.split("鍵", 1)[0], \
        "wiring.py に旧パス参照が残っている"


def test_ruff_clean_api():
    """src/backend/routers/, src/api/, src/interfaces/api/ が ruff check を通る。"""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src/backend/routers", "src/api", "src/interfaces/api"],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
    )
    assert result.returncode == 0, \
        f"ruff check 失敗:\n{result.stdout}\n{result.stderr}"
