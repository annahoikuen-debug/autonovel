#!/usr/bin/env python3
"""Step 1: import 依存グラフのスナップショット生成。

src/、config/、tests/ 以下の全 .py を走査し、
`from src.xxx import ...` / `import src.xxx` パターンを抽出して
var/import_graph.json に出力する。

出力形式:
{
    "src/agents/foo.py": ["src.domain.models.book", "src.core.llm"],
    ...
}

使い方:
    python scripts/generate_import_graph.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # リポジトリルート

# 走査対象ディレクトリ
TARGET_DIRS = [ROOT / "src", ROOT / "config", ROOT / "tests"]

# 出力先
OUTPUT_FILE = ROOT / "var" / "import_graph.json"

# 検出パターン
#   from src.pkg.sub import name
#   from src.pkg import name
#   import src.pkg.sub
IMPORT_PATTERN = re.compile(
    r"^\s*(?:from\s+(\S+?)\s+import\s+.*?|import\s+(\S+?))\s*(?:#.*)?$"
)


def is_python_file(path: Path) -> bool:
    return path.suffix == ".py" and "__pycache__" not in str(path)


def collect_imports(file_path: Path) -> list[str]:
    """ファイル内の src.* import を抽出して返す。"""
    imports: set[str] = set()
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    for line in content.splitlines():
        m = IMPORT_PATTERN.match(line)
        if not m:
            continue
        # from の場合 group(1)、import の場合 group(2)
        module = m.group(1) or m.group(2)
        if module and module.startswith("src."):
            # from a.b.c import d では "a.b.c" のみ記録（d は無視）
            imports.add(module)

    return sorted(imports)


def main() -> None:
    graph: dict[str, list[str]] = {}

    for target_dir in TARGET_DIRS:
        if not target_dir.exists():
            continue
        for py_file in sorted(target_dir.rglob("*.py")):
            if "__pycache__" in str(py_file):
                continue
            rel = str(py_file.relative_to(ROOT))
            deps = collect_imports(py_file)
            graph[rel] = deps

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"Generated {OUTPUT_FILE}")
    print(f"Files scanned: {len(graph)}")
    total_imports = sum(len(v) for v in graph.values())
    print(f"Total src.* imports found: {total_imports}")


if __name__ == "__main__":
    main()
