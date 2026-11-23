#!/usr/bin/env python3
r"""shim 参照数マトリクスを再生成する。

PLAN_Q3 Step 1。config/shim_registry.json に登録された全 shim について、
src/tests/config/scripts からの参照数を 3 段階（AST strict / 文字列 loose /
動的参照）でスキャンし、shadowing（同名ディレクトリによる到達不能）
を検出して Markdown テーブルを標準出力する。

設計方針（PLAN_R3 §0 / PLAN_Q2 P3 / PLAN_Q3 P4 を参照）:
  * スキャン対象は `git ls-files` で追跡済み .py を全件列挙（ルートの手動列挙を禁止）。
  * 接頭辞衝突を防ぐため (?<![\w.]) と \b 境界を必須化する。
  * shadowing: importlib.util.find_spec で、shim のパス（x.py）に対して
    同名ディレクトリ（x/）が存在し、そちらに解決する場合を shadowed とみなす。
    shadowed な shim は実行時に到達しないため、参照解消なしで削除可能。
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_py_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        return []
    return [REPO_ROOT / f for f in result.stdout.split("\0") if f]


def _module_path_regex(module_path: str) -> re.Pattern[str]:
    parts = re.split(r"[./]", module_path)
    pattern = r"(?<![\w.])" + r"[./]".join(re.escape(p) for p in parts) + r"\b"
    return re.compile(pattern)


def _strict_scan(text: str, regex: re.Pattern[str]) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names = [node.module] + [a.name for a in node.names]
        for name in names:
            if regex.search(name):
                return True
    return False


def _loose_scan(text: str, regex: re.Pattern[str]) -> bool:
    return bool(regex.search(text))


def _dynamic_scan(text: str, module_path: str) -> bool:
    call_regex = re.compile(r"(?:importlib\.import_module|__import__)\s*\(\s*[\"']([^\"']+)[\"']")
    for m in call_regex.finditer(text):
        if m.group(1) == module_path or m.group(1).replace("/", ".") == module_path:
            return True
    getattr_regex = re.compile(r"(?:getattr|setattr)\s*\([^,]+,\s*[\"']([^\"']+)[\"']")
    for m in getattr_regex.finditer(text):
        if module_path in m.group(1):
            return True
    return False


def _is_shadowed(shim_path: str) -> tuple[bool, str | None]:
    """shim のパス（src/x/y.py）に対して、同名ディレクトリ（src/x/y/）が
    存在し、そちらに import 解決されるかを判定する。"""
    p = REPO_ROOT / shim_path
    if not p.is_file() or p.suffix != ".py":
        return False, None
    dir_candidate = p.with_suffix("")
    if dir_candidate.is_dir() and (dir_candidate / "__init__.py").exists():
        # find_spec で実際の解決先を確認
        module_name = shim_path[:-3].replace("/", ".")
        spec = importlib.util.find_spec(module_name)
        if spec is not None and spec.origin is not None:
            resolved = Path(spec.origin)
            if resolved != p and resolved.parent == dir_candidate:
                return True, str(resolved.relative_to(REPO_ROOT))
    return False, None


def check_shim(shim: str, files: list[Path]) -> dict:
    # shim は "src/x/y.py" 形式。モジュールパスに変換。
    module_path = shim[:-3].replace("/", ".") if shim.endswith(".py") else shim
    regex = _module_path_regex(module_path)

    strict_hits: list[str] = []
    loose_only_hits: list[str] = []
    dynamic_hits: list[str] = []

    shim_py_path = shim.replace(".", "/") + ".py" if "." in shim else shim
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(f.relative_to(REPO_ROOT))
        if rel == shim_py_path:
            continue
        if _strict_scan(text, regex):
            strict_hits.append(rel)
        elif _loose_scan(text, regex):
            loose_only_hits.append(rel)
        if _dynamic_scan(text, module_path):
            dynamic_hits.append(rel)

    shadowed, resolved_to = _is_shadowed(shim)

    return {
        "shim": shim,
        "module": module_path,
        "strict_hits": strict_hits,
        "loose_only_hits": loose_only_hits,
        "dynamic_hits": dynamic_hits,
        "src_strict": [h for h in strict_hits if not h.startswith("tests/")],
        "tests_strict": [h for h in strict_hits if h.startswith("tests/")],
        "shadowed": shadowed,
        "shadowed_to": resolved_to,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="shim 参照数マトリクスを再生成")
    parser.add_argument(
        "--registry",
        default="config/shim_registry.json",
        help="shim レジストリ JSON ファイル",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Markdown テーブル形式で出力",
    )
    args = parser.parse_args()

    data = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    shims: list[str] = data.get("shims", [])

    files = _tracked_py_files()

    results = [check_shim(s, files) for s in shims]
    results.sort(key=lambda r: (-(len(r["src_strict"]) + len(r["tests_strict"])), r["shim"]))

    if args.markdown:
        print("| shim | src 参照 | tests 参照 | shadowed | 削除可否 |")
        print("|------|----------|------------|----------|----------|")
        for r in results:
            total_refs = len(r["src_strict"]) + len(r["tests_strict"])
            deletable = total_refs == 0 or r["shadowed"]
            verdict = "✓ 削除可" if deletable else "✗ 参照あり"
            shadowed_mark = "🌑" if r["shadowed"] else ""
            print(f"| {r['shim']} | {len(r['src_strict'])} | {len(r['tests_strict'])} | {shadowed_mark} | {verdict} |")
        print()
        print(f"合計: {len(results)} 件の shim")
        deletable_count = sum(
            1 for r in results if (len(r["src_strict"]) + len(r["tests_strict"]) == 0) or r["shadowed"]
        )
        print(f"削除可能: {deletable_count} 件 / 参照あり: {len(results) - deletable_count} 件")
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
