"""BookMapper が旧レイアウト (src.backend / src.services / src.agents) に依存しないことを AST で固定する。

TRACK-A4 のリグレッション防止テスト。
book_mapper モジュールをソースコードとして構文解析し、src.backend / src.services / src.agents を
import しないことを assert する。
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "src" / "infrastructure" / "database" / "mappers" / "book_mapper.py"

LEGACY_PREFIXES = ("src.backend", "src.services", "src.agents")


def _collect_import_prefixes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    prefixes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if len(parts) >= 2 and parts[0] == "src":
                    prefixes.add(f"src.{parts[1]}")
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            if node.module:
                parts = node.module.split(".")
                if len(parts) >= 2 and parts[0] == "src":
                    prefixes.add(f"src.{parts[1]}")
    return prefixes


def test_book_mapper_no_legacy_import():
    """book_mapper.py が src.backend / src.services / src.agents を import しないこと."""
    prefixes = _collect_import_prefixes(TARGET)
    violations = sorted(p for p in prefixes if p.startswith(LEGACY_PREFIXES))
    assert not violations, (
        f"book_mapper.py が旧レイヤーを import しています: {violations}\n"
        f"ポート (src.infrastructure.database.models.*) 経由に置き換えてください。"
    )


def test_collect_import_prefixes_detects_legacy():
    """検出器自体の動作確認."""
    import tempfile

    code = "from src.backend.database.models import Book\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp = Path(f.name)
    try:
        prefixes = _collect_import_prefixes(tmp)
        assert "src.backend" in prefixes
    finally:
        tmp.unlink()
