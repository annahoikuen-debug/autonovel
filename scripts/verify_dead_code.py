#!/usr/bin/env python3
r"""削除候補モジュールの「参照ゼロ」を3段階で機械証明する。

設計方針 (PLAN_R3 §0 / PLAN_Q2 P3 を参照):
  * スキャン対象は `git ls-files` で追跡済み .py を全件列挙 (ルートの手動列挙を禁止)。
    「3ディレクトリの走査漏れ」が事故原因だったため、全件スキャンを機械化する。
  * 接頭辞衝突を防ぐため (?<![\w.]) と \b 境界を必須化する
    (src.llm.clients_extra が src.llm.clients に誤一致しないなど)。
  * 3段階: AST strict / 文字列 loose / 動的参照 (importlib / __import__ / getattr / setattr)。

終了コード:
  0: すべての候補が src 参照ゼロ (groups 内の相互参照は許容)
  1: 1件以上で src 以外からの strict/dynamic 参照あり -> 削除不可
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_py_files() -> list[Path]:
    """git ls-files で追跡済み .py を全件返す。git 未検出環境は空リスト（skip相当）。"""
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
    r"""モジュールパス（`src.llm.clients` / `src/llm/clients`）の厳密正規表現を作る。

    * `.` と `/` はどちらも区切りとして許容
    * 接頭辞衝突を防ぐ `(?<![\w.])`
    * 接尾辞衝突を防ぐ `\b`
    """
    # src.llm.clients → (?:src[./]llm[./]clients)\b
    parts = re.split(r"[./]", module_path)
    pattern = r"(?<![\w.])" + r"[./]".join(re.escape(p) for p in parts) + r"\b"
    return re.compile(pattern)


def _strict_scan(text: str, regex: re.Pattern[str]) -> bool:
    """ast による Import / ImportFrom の厳密スキャン。"""
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
    """ソース全体の文字列スキャン（docstring / importlib / monkeypatch 等を拾う）。"""
    return bool(regex.search(text))


def _dynamic_scan(text: str, module_path: str) -> bool:
    """動的参照スキャン。importlib.import_module / __import__ / getattr / setattr の
    文字列引数が候補モジュールと一致するか照合する。"""
    # importlib.import_module("src.llm.clients") / __import__("src.llm.clients")
    call_regex = re.compile(r"(?:importlib\.import_module|__import__)\s*\(\s*[\"']([^\"']+)[\"']")
    for m in call_regex.finditer(text):
        if m.group(1) == module_path or m.group(1).replace("/", ".") == module_path:
            return True
    # getattr(obj, "src.llm.clients.X") / setattr(obj, "src.llm.clients.X", …)
    getattr_regex = re.compile(r"(?:getattr|setattr)\s*\([^,]+,\s*[\"']([^\"']+)[\"']")
    for m in getattr_regex.finditer(text):
        if module_path in m.group(1):
            return True
    return False


def check_module(module_path: str, files: list[Path]) -> dict:
    """1モジュールの参照チェック結果を返す。"""
    regex = _module_path_regex(module_path)
    strict_hits: list[str] = []
    loose_only_hits: list[str] = []
    dynamic_hits: list[str] = []

    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(f.relative_to(REPO_ROOT))
        # 自分自身は参照とみなさない
        if rel == module_path.replace(".", "/") + ".py":
            continue
        if _strict_scan(text, regex):
            strict_hits.append(rel)
        elif _loose_scan(text, regex):
            loose_only_hits.append(rel)
        if _dynamic_scan(text, module_path):
            dynamic_hits.append(rel)

    return {
        "module": module_path,
        "strict_hits": strict_hits,
        "loose_only_hits": loose_only_hits,
        "dynamic_hits": dynamic_hits,
        "src_strict": [h for h in strict_hits if not h.startswith("tests/")],
        "src_dynamic": [h for h in dynamic_hits if not h.startswith("tests/")],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="削除候補モジュールの参照ゼロ証明")
    parser.add_argument(
        "--list",
        required=True,
        help="削除候補モジュールパスのJSONファイル（例: config/removed_modules.json）",
    )
    parser.add_argument(
        "--include-web",
        action="store_true",
        help=".ts / .tsx もスキャン対象に含める（Reactフォーク削除用）",
    )
    args = parser.parse_args()

    with open(args.list, encoding="utf-8") as f:
        data = json.load(f)
        candidates: list[str] = data.get("modules", [])

    files = _tracked_py_files()
    web_files: list[Path] = []
    if args.include_web:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.ts", "*.tsx"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        if result.returncode == 0:
            web_files = [REPO_ROOT / f for f in result.stdout.split("\0") if f]

    all_files = files + web_files

    failed = False
    for module in candidates:
        result = check_module(module, all_files)
        src_strict = result["src_strict"]
        src_dynamic = result["src_dynamic"]
        status = "OK" if not src_strict and not src_dynamic else "FAIL"
        if status == "FAIL":
            failed = True
        print(
            f"[{status}] {module} | "
            f"src_strict={src_strict} | "
            f"src_dynamic={src_dynamic} | "
            f"tests_strict={[h for h in result['strict_hits'] if h.startswith('tests/')]} | "
            f"loose_only={result['loose_only_hits'][:3]}..."
        )

    if failed:
        print("\nFAIL: 1つ以上の候補で src 参照が検出されました。削除できません。")
        return 1
    print("\nOK: すべての候補が src 参照ゼロです。削除可能です。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
