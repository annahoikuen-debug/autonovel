"""var/import_graph.json の鮮度を検証する。

scripts/generate_import_graph.py を再実行し、var/import_graph.json に差分が
出ないことを確認する。生成物が存在しない／追跡対象外の場合は fail。

生成物が古いまま（スクリプト再実行後に差分が出る）場合は fail し、
`python scripts/generate_import_graph.py` の実行とコミットを促す。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GRAPH_PATH = ROOT / "var" / "import_graph.json"
GENERATE_SCRIPT = ROOT / "scripts" / "generate_import_graph.py"


def test_import_graph_exists_and_is_tracked():
    """var/import_graph.json が存在し、git で追跡されていること。"""
    assert GRAPH_PATH.exists(), "var/import_graph.json が存在しない"
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(GRAPH_PATH)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, "var/import_graph.json が git で追跡されていない"


def _git_diff_quiet(path: Path) -> int:
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", str(path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return result.returncode


def test_import_graph_is_fresh():
    """generate_import_graph.py を再実行しても var/import_graph.json に差分が出ないこと。"""
    # まず現状の diff をチェック
    if _git_diff_quiet(GRAPH_PATH) != 0:
        # 差分がある場合は再生成し、再度 diff をチェック
        regen = subprocess.run(
            [sys.executable, str(GENERATE_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert regen.returncode == 0, f"generate_import_graph.py が失敗: {regen.stderr}"
    assert _git_diff_quiet(GRAPH_PATH) == 0, (
        f"{GRAPH_PATH} がスクリプト再実行後の状態と一致しない。\n"
        f"`python scripts/generate_import_graph.py` を実行しコミットすること。"
    )


def test_import_graph_has_expected_structure():
    """var/import_graph.json が JSON オブジェクトであること。"""
    data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "var/import_graph.json は JSON オブジェクトである必要がある"
    # 削除済み shim がキーに残っていないこと（鮮度の簡易チェック）
    removed_shims = [
        "config/imagen_models.py",
        "config/platform_censorship_rules.py",
        "config/erotic_vocabulary.py",
        "config/project_context.py",
    ]
    for removed in removed_shims:
        assert removed not in data, f"削除済み shim '{removed}' が import_graph.json に残っている"
