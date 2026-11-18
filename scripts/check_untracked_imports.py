"""追跡ゼロの Python パッケージを import するテストを機械的に検出する。

clean checkout（git の追跡対象外ファイルがない環境）で import 時に
ModuleNotFoundError で落ちるテストを未然に防ぐ。

検出ロジック:
  1. `git ls-files -- '*.py'` で追跡中の .py ファイル集合を取得
  2. 各ファイルから「モジュールパス」を構築（src/core/llm.py → src.core.llm）
     ディレクトリ配下の __init__.py はパッケージとして認識
  3. tests/**/*.py から import 文（import X / from X import / importlib.import_module("X")）
     のモジュールパスを抽出（対象は `src.` 始まりのみ。`prompts.` 等は対象外）
  4. 存在しないモジュールパスを import しているテストを報告し、exit 1

既知の制限（静的解析のため検出できないケース）:
  - 変数経由の importlib.import_module(module_path) は、モジュールスコープの
    代入リテラルおよび @pytest.mark.parametrize で渡されるリスト名から AST で
    解決する（このスクリプト内で実装）。f-string 等で動的に組み立てたパスや、
    関数スコープ局所変数経由の import は依然として検出できない。
    → 実例: tests/regression/test_shim_imports.py の KNOWN_SHIMS は AST 解決の網に
    かかるため、本チェックで検出可能。
  - 勹的に組み立てた import（f"src.{name}" 等）。
  - 上記を検出するには pytest 実行時の import エラー（conftest/モジュールレベル import）
    を収集する別ゲートが必要。

Usage:
  python scripts/check_untracked_imports.py                        # CI 用（失敗で exit 1）
  python scripts/check_untracked_imports.py --list                 # 検出対象のみ一覧表示
  python scripts/check_untracked_imports.py --allowlist PATH       # allowlist ファイルを指定（既定: config/untracked_imports_allowlist.json）
  python scripts/check_untracked_imports.py --strict               # allowlist にあるが実際には存在する
                                              エントリ（陳腐化）でも fail させる
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
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
        # 変数経由の importlib.import_module(...) は正規表現では捕捉できないため、
        # import 文が 1 つもないファイルも走査対象に含める。
        result[str(f.relative_to(ROOT))] = imports
    return result


def _load_allowlist(path: Path) -> set[tuple[str, str]]:
    """allowlist JSON を読み込み、(test_file, module) のセットを返す。"""
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    return {(e["test"], e["module"]) for e in entries}


def _literal_string_targets(node: ast.AST) -> list[str]:
    """リスト/タプル/セット/辞書リテラルから、モジュールパス文字列を抽出する。

    (module_path, symbols) 形式のタプル/リストでは先頭要素を、それ以外の
    文字列リテラル要素をそのまま返す。src.* 始まり以外は呼び出し側で除外する。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        out: list[str] = []
        for e in node.elts:
            if (
                isinstance(e, (ast.List, ast.Tuple))
                and e.elts
                and isinstance(e.elts[0], ast.Constant)
                and isinstance(e.elts[0].value, str)
            ):
                out.append(e.elts[0].value)
            elif isinstance(e, ast.Constant) and isinstance(e.value, str):
                out.append(e.value)
        return out
    if isinstance(node, ast.Dict):
        return [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    return []


def _resolve_variable_imports(text: str) -> list[tuple[str, int]]:
    """importlib.import_module(変数) を module-scope 代入リテラル /
    @pytest.mark.parametrize 経由で解決し、(module_path, lineno) を返す。

    src.* 始まりのみを対象とする（patch() の属性パス等を混ぜない）。
    関数スコープ局所変数や f-string 組み立ては解決対象外。
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    # モジュールスコープ代入: NAME = リテラル
    module_assigns: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            module_assigns[node.targets[0].id] = node.value

    results: list[tuple[str, int]] = []

    def handle_function(func: ast.AST) -> None:
        # @pytest.mark.parametrize("a,b", LISTNAME) -> name -> list_name マップ
        pmap: dict[str, str] = {}
        for dec in getattr(func, "decorator_list", []):
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr == "parametrize"
                and len(dec.args) >= 2
                and isinstance(dec.args[0], ast.Constant)
                and isinstance(dec.args[0].value, str)
                and isinstance(dec.args[1], ast.Name)
            ):
                for name in dec.args[0].value.split(","):
                    pmap[name.strip()] = dec.args[1].id

        for node in ast.walk(func):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
                and node.args
            ):
                continue
            arg = node.args[0]
            if not isinstance(arg, ast.Name):
                continue
            target_name = arg.id
            source = module_assigns.get(target_name)
            if source is None and target_name in pmap:
                source = module_assigns.get(pmap[target_name])
            if source is None:
                continue
            for m in _literal_string_targets(source):
                if m.startswith("src."):
                    results.append((m, node.lineno))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            handle_function(node)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    handle_function(sub)

    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="検出対象の import 箇所のみ一覧表示")
    ap.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST, help="allowlist JSON のパス")
    ap.add_argument("--strict", action="store_true", help="allowlist にあるが実際には存在するエントリ（陳腐化）でも fail にする")
    args = ap.parse_args()

    modules, tracked_files = _tracked_state()
    tests = _scan_tests()
    allowlist = _load_allowlist(args.allowlist)

    missing: list[tuple[str, str, str]] = []  # (test_file, module_path, line_context)
    allowlisted_but_exists: list[tuple[str, str]] = []  # allowlist にあるが実際には存在するもの
    for test_file, imports in tests.items():
        text = (ROOT / test_file).read_text(encoding="utf-8")
        lines = text.splitlines()
        seen: set[tuple[str, str]] = set()
        for i, line in enumerate(lines, start=1):
            for m in _extract_imports(line):
                key = (test_file, m)
                if key in seen:
                    continue
                seen.add(key)
                if key in allowlist:
                    if _module_exists(m, modules, tracked_files, ROOT):
                        allowlisted_but_exists.append(key)
                    continue
                if not _module_exists(m, modules, tracked_files, ROOT):
                    missing.append((test_file, m, line.strip()))

        # 変数経由の importlib.import_module(...) を AST で解決
        for m, lineno in _resolve_variable_imports(text):
            key = (test_file, m)
            if key in seen:
                continue
            seen.add(key)
            if key in allowlist:
                if _module_exists(m, modules, tracked_files, ROOT):
                    allowlisted_but_exists.append(key)
                continue
            if not _module_exists(m, modules, tracked_files, ROOT):
                missing.append((test_file, m, lines[lineno - 1].strip()))

    if allowlisted_but_exists:
        print("WARN: 以下の allowlist エントリは実際にはモジュールが存在するため不要です:")
        for test_file, module in allowlisted_but_exists:
            print(f"  {test_file}:{module}")
        if args.strict:
            print("FAIL: --strict が指定されているため、陳腐化 allowlist エントリで exit 1 します。")
            return 1
    if missing:
        print(
            "ERROR: テストから追跡ゼロのモジュールを import しています（clean checkout で ModuleNotFoundError になります）:"
        )
        for test_file, module, line in missing:
            print(f"  {test_file}:{module}  <- {line}")
        if not args.list:
            return 1
    else:
        print("OK: すべてのテスト import は追跡中のモジュールを参照しています（または allowlist 登録済み）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
