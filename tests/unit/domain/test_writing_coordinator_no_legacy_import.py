"""WritingCoordinator が旧レイアウト (src.agents / src.services) に依存しないことを AST で固定する。

TRACK-A1 のリグレッション防止テスト。
coordinator モジュールをソースコードとして構文解析し、トップレベルおよび
関数内の lazy import を含め、src.agents / src.services / src.backend を
import しないことを assert する。

このテストが赤になった場合、coordinator.py に新たな旧レイヤー依存が
追加されたことを意味する。ポート経由の DI に置き換えること。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "src" / "domain" / "writing" / "coordinator.py"

# 契約2 の対象となる旧来の巨大モノリス。これらを import すると違反。
LEGACY_PREFIXES = ("src.agents", "src.services", "src.backend")


def _collect_import_prefixes(path: Path) -> set[str]:
    """ファイル内の全 import 文から src.<top> 接頭辞を収集する。

    関数内の lazy import (ast.ImportFrom / ast.Import を ast.walk で走査)
    も漏れなく検出する。
    """
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
                continue  # 相対 import は同一パッケージ内
            if node.module:
                parts = node.module.split(".")
                if len(parts) >= 2 and parts[0] == "src":
                    prefixes.add(f"src.{parts[1]}")
    return prefixes


def test_writing_coordinator_no_legacy_import():
    """coordinator.py が src.agents / src.services / src.backend を import しないこと."""
    prefixes = _collect_import_prefixes(TARGET)
    violations = sorted(p for p in prefixes if p.startswith(LEGACY_PREFIXES))
    assert not violations, (
        f"coordinator.py が旧レイヤーを import しています: {violations}\n"
        f"ポート (src.application.ports.*) 経由の DI に置き換えてください。"
    )


def test_collect_import_prefixes_detects_legacy():
    """検出器自体の動作確認: 意図的に旧レイヤー import を含むモジュールを検出できる."""
    import tempfile

    code = "from src.agents.specialists.unified_auditor import UnifiedAuditor\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp = Path(f.name)
    try:
        prefixes = _collect_import_prefixes(tmp)
        assert "src.agents" in prefixes
    finally:
        tmp.unlink()
        sys.modules.pop(tmp.stem, None)
