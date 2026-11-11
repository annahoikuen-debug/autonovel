"""Phase R3 手順 4: 削除済み shim の検出テスト (SHIM_REMOVAL_PLAN)。

削除済み shim について以下を assert する:

1. shim ファイルが存在しないこと
2. 旧パスでの import が ModuleNotFoundError で失敗すること
3. config/shim_registry.json に未登録であること
4. リポジトリ内のソースから旧パスを参照するファイルが 1 つも無いこと

4 は fee262b1 類の事故（参照解消を飛ばした shim 削除）を 1 コミットで
検出するための中核チェックである。
"""

from __future__ import annotations

import ast
import importlib
import json
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config" / "shim_registry.json"

#: Phase R3-1 (config/) で既に削除済みの shim 一覧
#: 新たに削除する shim は、削除コミットと同一にここに追加すること。
REMOVED_SHIMS: list[str] = [
    "config/image_models.py",
    "config/imagen_models.py",
    "config/cors_config.py",
    "config/file_watcher.py",
    "config/platform_censorship_rules.py",
    "config/emotional_hook_vocabulary.py",
    "config/logging_config.py",
    "config/narrative.py",
    "config/streamlit_adapter.py",
    "config/archetypes.py",
    "config/styles.py",
    "config/validator.py",
    "config/domain_profile_manager.py",
    "config/settings.py",
    "config/project_context.py",
    "config/archetypes_new.py",
    "config/constants.py",
    "config/container.py",
    "config/models.py",
    "config/sharp_edge_vocabulary.py",
    "config/erotic_direct_mappings.py",
    "config/erotic_pacing.py",
    "config/erotic_parameters.py",
    "config/erotic_platform_presets.py",
    "config/erotic_thresholds.py",
    "config/erotic_video_patterns.py",
    "config/erotic_vocabulary.py",
    "config/erotic_vocabulary_ext.py",
]

registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
REGISTERED: set[str] = set(registry.get("shims", []))


@lru_cache(maxsize=1)
def _strict_import_modules() -> set[str]:
    """追跡済み .py 全ファイルから ast で import 対象モジュールを収集する。

    collection 時に毎回 2780 ファイルを read+ast.parse すると
    collection が +6〜10s 増大し、collection speed ゲート（30s 予算）を超過するため、
    初回呼び出し時にのみ実行し結果をキャッシュする。
    """
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    modules: set[str] = set()
    for p in result.stdout.split("\x00"):
        if not p:
            continue
        py_file = ROOT / p
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
    return modules


@pytest.mark.parametrize("shim_path", REMOVED_SHIMS)
def test_removed_shim_file_does_not_exist(shim_path):
    """削除済み shim ファイルが存在しないこと。"""
    assert not (ROOT / shim_path).exists(), f"{shim_path} がまだ存在する"


@pytest.mark.parametrize("shim_path", REMOVED_SHIMS)
def test_removed_shim_import_fails(shim_path):
    """削除済み shim の旧パス import が ModuleNotFoundError で失敗すること。"""
    mod = shim_path[:-3].replace("/", ".")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(mod)


@pytest.mark.parametrize("shim_path", REMOVED_SHIMS)
def test_removed_shim_not_in_registry(shim_path):
    """削除済み shim が shim_registry.json に未登録であること。"""
    assert shim_path not in REGISTERED, f"{shim_path} が registry に残っている"


@pytest.mark.parametrize("shim_path", REMOVED_SHIMS)
def test_removed_shim_has_no_referencing_source(shim_path):
    """削除済み shim の旧パスを参照するソースが 1 つも無いこと。

    fee262b1 類の事故（参照解消を飛ばした削除）を検出する。
    """
    mod = shim_path[:-3].replace("/", ".")
    referencing = sorted(m for m in _strict_import_modules() if m == mod or m.startswith(mod + "."))
    assert not referencing, (
        f"{shim_path} ({mod}) を参照するソースがまだ残っている: {referencing}\n"
        "削除前に全参照を新パスへ置換すること。"
    )
