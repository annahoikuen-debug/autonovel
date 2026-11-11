"""Step 27: config 4箇所の統合が完了し、全 import 経路が動作することを確認する。

config/ の Python コードが src/ 配下の正規レイヤーに移動し、
旧パスの shim も含めて全経路が正しく動作することを検証する。

注: streamlit_adapter は streamlit モジュールが必要なため、
このテストでは import 可否のみを確認（モジュール未導入時はスキップ）。
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: 全ての config 関連 import 経路 (module_path, expected_symbols_or_None)
#: symbols が None の場合は import 成功のみを確認。
CONFIG_IMPORT_PATHS = [
    # 新パス（統合後）- 第1バッチ: src/config/
    ("src.config.archetypes", None),
    ("src.config.archetypes_new", None),
    ("src.config.constants", None),
    ("src.config.domain_profile_manager", None),
    ("src.config.emotional_hook_vocabulary", None),
    ("src.config.image_models", None),
    ("src.config.imagen_models", None),
    ("src.config.platform_censorship_rules", None),
    ("src.config.sharp_edge_vocabulary", None),
    # 新パス（統合後）- 第2バッチ: src/infrastructure/config/
    ("src.infrastructure.config.cors_config", None),
    ("src.infrastructure.config.file_watcher", None),
    ("src.infrastructure.config.logging_config", None),
    ("src.infrastructure.config.project_context", None),
    ("src.infrastructure.config.validator", None),
    ("src.infrastructure.config.settings", ["settings", "Settings", "ROOT_DIR"]),
    # 新パス（統合後）- 第3バッチ: src/domain/, src/interfaces/
    ("src.domain.models.config_models", None),
    ("src.domain.narrative", None),
    ("src.domain.styles", None),
    ("src.interfaces.streamlit_adapter", None),
    # 旧パス（shim、維持必須）- 第1バッチ
    ("config.archetypes", None),
    ("config.archetypes_new", None),
    ("config.constants", None),
    ("config.domain_profile_manager", None),
    ("config.emotional_hook_vocabulary", None),
    ("config.sharp_edge_vocabulary", None),
    ("config.logging_config", None),
    ("config.project_context", None),
    ("config.validator", None),
    ("config.settings", ["settings", "Settings"]),
    # 旧パス（shim、維持必須）- 第3バッチ
    ("config.models", None),
    ("config.narrative", None),
    ("config.styles", None),
    # 旧パス（shim、維持必須）- 既存
    ("config.container", ["Container", "get_container"]),
    # erotic shims（既存、維持必須）
    ("config.erotic_vocabulary", ["METAPHOR_BANK"]),
]


@pytest.mark.parametrize("module_path,symbols", CONFIG_IMPORT_PATHS)
def test_all_config_import_paths(module_path, symbols):
    """全ての config import 経路が動作する。"""
    try:
        mod = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        # streamlit 等のオプション依存不足はスキップ
        if "streamlit" in str(exc) or "watchdog" in str(exc):
            pytest.skip(f"{module_path}: オプション依存不足 ({exc})")
        pytest.fail(f"{module_path} の import に失敗: {exc}")
    except ImportError as exc:
        if "streamlit" in str(exc) or "watchdog" in str(exc):
            pytest.skip(f"{module_path}: オプション依存不足 ({exc})")
        pytest.fail(f"{module_path} の import に失敗: {exc}")

    if symbols is not None:
        for symbol in symbols:
            assert hasattr(mod, symbol), \
                f"{module_path} に {symbol} が公開されていない"


def test_no_orphan_config_files():
    """移動元に不要な実体ファイルが残っていない。"""
    # 移動元ディレクトリが shim のみになっていることを確認
    moved_files = [
        "config/archetypes.py",
        "config/archetypes_new.py",
        "config/constants.py",
        "config/domain_profile_manager.py",
        "config/emotional_hook_vocabulary.py",
        "config/sharp_edge_vocabulary.py",
        "config/logging_config.py",
        "config/project_context.py",
        "config/validator.py",
        "config/models.py",
        "config/narrative.py",
        "config/styles.py",
        "config/streamlit_adapter.py",
    ]
    for fname in moved_files:
        path = ROOT / fname
        if path.exists():
            content = path.read_text(encoding="utf-8")
            assert "shim" in content.lower() or "後方互換" in content, \
                f"{path} が shim ではなく実体ファイルとして残っている"


def test_config_yaml_intact():
    """config/ の YAML ファイルが無傷である。"""
    config_dir = ROOT / "config"
    yaml_files = list(config_dir.glob("*.yaml")) + list(config_dir.glob("*.yml"))
    assert len(yaml_files) > 10, f"config/ の YAML ファイルが少なすぎ: {len(yaml_files)}"


def test_ruff_clean_config():
    """src/config/, src/infrastructure/config/, src/domain/, src/interfaces/ が ruff check を通る。"""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check",
         "src/config", "src/infrastructure/config", "src/domain", "src/interfaces"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, \
        f"ruff check 失敗:\n{result.stdout}\n{result.stderr}"
