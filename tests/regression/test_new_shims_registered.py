"""Step 5: 新しい shim が shim_registry.json に登録されていることを確認する。

src/ と config/ 以下の全 .py ファイルを走査し、「後方互換 shim」または
「Compatibility shim」を含むファイルがすべて shim_registry.json に
登録されていることを検証する。

新しい shim を作成したら、config/shim_registry.json に追加すること。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

SHIM_MARKERS = ["後方互換 shim", "Compatibility shim", "後方互換ラッパー"]


def test_all_shims_registered():
    """全ての shim ファイルが shim_registry.json に登録されている。"""
    registry_path = ROOT / "config" / "shim_registry.json"
    assert registry_path.exists(), "config/shim_registry.json が存在しない"

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registered = set(registry.get("shims", []))

    # src/ と config/ 以下の全 .py を走査
    discovered = set()
    for base in [ROOT / "src", ROOT / "config"]:
        if not base.exists():
            continue
        for py_file in base.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(marker in content for marker in SHIM_MARKERS):
                rel = str(py_file.relative_to(ROOT))
                discovered.add(rel)

    unregistered = discovered - registered
    assert not unregistered, (
        f"未登録の shim: {sorted(unregistered)}\n"
        f"config/shim_registry.json に追加してください"
    )
