"""Step 32: スキーマ 6箇所の統合が完了し、全経路が動作することを確認する。

スキーマ/モデルが分散していた場所（src/models/, src/domain/models/,
src/domain/schemas/, src/schemas/, ルートschemas/, src/types/）を整理し、
旧パスの shim も含めて全経路が正しく動作することを検証する。
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: スキーマ関連 import 経路 (module_path, expected_symbols_or_None)
SCHEMA_IMPORT_PATHS = [
    # src.models (Pydantic スキーマ群)
    ("src.models", None),
    ("src.models.api_schemas", None),
    ("src.models.base", None),
    ("src.models.db", None),
    ("src.models.character", None),
    ("src.models.editor", None),
    ("src.models.graph_schemas", None),
    ("src.models.narrative_metrics_db", None),
    # src.domain.models (ドメインモデル)
    ("src.domain.models", None),
    ("src.domain.models.book", None),
    ("src.domain.models.character", None),
    ("src.domain.models.bible", None),
    ("src.domain.models.chapter", None),
    ("src.domain.models.branch", None),
    ("src.domain.models.plot", None),
    ("src.domain.models.prompt_version", None),
    # src.domain.schemas (ドメインスキーマ)
    ("src.domain.schemas", None),
    ("src.domain.schemas.easy_mode", None),
    # src.schemas (shim、維持必須)
    ("src.schemas", None),
    # ルート schemas/ （配布用、移動なし）
    # （存在する場合のみ確認）
]

# ルート schemas/ の存在確認
ROOT_SCHEMAS = ROOT / "schemas"
if ROOT_SCHEMAS.exists():
    for py_file in sorted(ROOT_SCHEMAS.glob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        mod_name = f"schemas.{py_file.stem}"
        SCHEMA_IMPORT_PATHS.append((mod_name, None))


@pytest.mark.parametrize("module_path,symbols", SCHEMA_IMPORT_PATHS)
def test_all_schema_import_paths(module_path, symbols):
    """全てのスキーマ import 経路が動作する。"""
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        pytest.fail(f"{module_path} の import に失敗: {exc}")
    if symbols is not None:
        for symbol in symbols:
            assert hasattr(mod, symbol), \
                f"{module_path} に {symbol} が公開されていない"


def test_no_ts_in_src_types():
    """src/types/ ディレクトリ（TypeScript 混入場所）が存在しない。"""
    types_dir = ROOT / "src" / "types"
    assert not types_dir.exists(), f"src/types/ が残っている: {types_dir}"


def test_schemas_shim():
    """src.schemas の shim が動作する。"""
    mod = importlib.import_module("src.schemas")
    assert mod is not None

def test_domain_schemas_easy_mode():
    """src.domain.schemas.easy_mode が import 可能。"""
    from src.domain.schemas import easy_mode  # noqa: F401

def test_models_importable():
    """src.models が import 可能。"""
    importlib.import_module("src.models")
