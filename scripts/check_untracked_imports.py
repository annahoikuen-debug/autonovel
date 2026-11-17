"""追跡ゼロの Python パッケージを import するテストを機械的に検出する。

clean checkout（git の追跡対象外ファイルがない環境）で import 時に
ModuleNotFoundError で落ちるテストを未然に防ぐ。

検出ロジック:
  1. `git ls-files -- '*.py'` で追跡中の .py ファイル集合を取得
  2. 各ファイルから「モジュールパス」を構築（src/core/llm.py → src.core.llm）
     ディレクトリ配下の __init__.py はパッケージとして認識
  3. tests/**/*.py から import 文（import X / from X import / importlib.import_module("X")）
     のモジュールパスを抽出
  4. 存在しないモジュールパスを import しているテストを報告し、exit 1

Usage:
  python scripts/check_untracked_imports.py                        # CI 用（失敗で exit 1）
  python scripts/check_untracked_imports.py --list                 # 検出対象のみ一覧表示
  python scripts/check_untracked_imports.py --allowlist PATH       # allowlist ファイルを指定（既定: config/untracked_imports_allowlist.json）
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = ROOT / "config" / "untracked_imports_allowlist.json"

# tests 配下のみスキャン（src 実コードは別ゲートでカバー）
TEST_GLOB = "tests/**/*.py"

# import 文の正規表現（モジュールパス部分をキャプチャ）
IMPORT_RE = re.compile(
    r"""(?:^\s*import\s+([\w.]+)|           # import foo.bar
         ^\s*from\s+([\w.]+)\s+import|       # from foo.bar import baz
         importlib\.import_module\(\s*["']([\w.]+)["']\))""",  # importlib.import_module("foo.bar")
    re.MULTILINE | re.VERBOSE,
)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


def _tracked_state() -> tuple[set[str], set[str]]:
    """git で追跡中の .py ファイルから、モジュールパス集合と追跡ファイルパス集合を返す。

    戻り値: (tracked_modules, tracked_files)
      tracked_modules: 存在するモジュールパス集合（src.core.llm など）
      tracked_files:   追跡中のファイル相対パス集合（src/core/llm.py など）
    """
    p = _run(["git", "ls-files", "--", "*.py"])
    tracked_files = set(p.stdout.splitlines())

    modules: set[str] = set()
    for f in tracked_files:
        rel = Path(f)
        if rel.suffix != ".py":
            continue
        # src/core/llm.py → src.core.llm
        modules.add(".".join(rel.with_suffix("").parts))

        # src/core/llm/__init__.py → src.core.llm（パッケージとして認識）
        if rel.name == "__init__.py":
            modules.add(".".join(rel.parent.parts))

    return modules, tracked_files


def _module_exists(m: str, modules: set[str], tracked_files: set[str], root: Path) -> bool:
    """モジュールパス m が追跡中に存在するか判定する。

    1. m 自体が tracked モジュールパスに含まれる（.py ファイルまたは __init__.py ディレクトリ）
    2. m に対応するディレクトリ内に tracked な .py ファイルが 1 つでもある
       （__init__.py なしの namespace package として動作するケース）
    """
    if m in modules:
        return True

    dir_path = root / Path(*m.split("."))
    if dir_path.is_dir():
        for f in dir_path.rglob("*.py"):
            if str(f.relative_to(root)) in tracked_files:
                return True

    return False


def _extract_imports(text: str) -> list[str]:
    """ソースコードから import 対象モジュールパスを抽出する。

    プロジェクト内モジュール（src.*）のみを対象とする。
    標準ライブラリ・サードパーティパッケージは自動的に除外される。
    """
    return [m for m in IMPORT_RE.findall(text) for m in m if m and m.startswith("src.")]


def _scan_tests() -> dict[str, list[str]]:
    """tests/**/*.py をスキャンし、ファイルごとの import モジュールパスを返す。"""
    result: dict[str, list[str]] = {}
    for f in sorted(ROOT.glob(TEST_GLOB)):
        text = f.read_text(encoding="utf-8")
        imports = _extract_imports(text)
        if imports:
            result[str(f.relative_to(ROOT))] = imports
    return result


def _load_allowlist(path: Path) -> set[tuple[str, str]]:
    """allowlist JSON を読み込み、(test_file, module) のセットを返す。"""
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    return {(e["test"], e["module"]) for e in entries}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="検出対象の import 箇所のみ一覧表示")
    ap.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST, help="allowlist JSON のパス")
    args = ap.parse_args()

    modules, tracked_files = _tracked_state()
    tests = _scan_tests()
    allowlist = _load_allowlist(args.allowlist)

    missing: list[tuple[str, str, str]] = []  # (test_file, module_path, line_context)
    allowlisted_but_exists: list[tuple[str, str]] = []  # allowlist にあるが実際には存在するもの
    for test_file, imports in tests.items():
        text = (ROOT / test_file).read_text(encoding="utf-8")
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            for m in _extract_imports(line):
                key = (test_file, m)
                if key in allowlist:
                    if _module_exists(m, modules, tracked_files, ROOT):
                        allowlisted_but_exists.append(key)
                    continue
                if not _module_exists(m, modules, tracked_files, ROOT):
                    missing.append((test_file, m, line.strip()))

    if allowlisted_but_exists:
        print("WARN: 以下の allowlist エントリは実際にはモジュールが存在するため不要です:")
        for test_file, module in allowlisted_but_exists:
            print(f"  {test_file}:{module}")
    if missing:
        print("ERROR: テストから追跡ゼロのモジュールを import しています（clean checkout で ModuleNotFoundError になります）:")
        for test_file, module, line in missing:
            print(f"  {test_file}:{module}  <- {line}")
        if not args.list:
            return 1
    else:
        print("OK: すべてのテスト import は追跡中のモジュールを参照しています（または allowlist 登録済み）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
