"""静的解析の「劣化のみ検出」ratchet。

ベースライン JSON に記録された件数を超えたら fail する。
ベースラインを下げることで改善を追えるが、
「全エラー 0 化」を目的とはしない (PLAN_H1 §9 で対象外と明記)。

対象:
  ruff   : `ruff check src tests config scripts` のエラー数
  mypy   : `mypy src` のエラー数
  format : `ruff format --check src` の「整形が必要なファイル数」

使い方:
  python scripts/ci_lint_ratchet.py                 # ruff（後方互換）
  python scripts/ci_lint_ratchet.py --tool mypy
  python scripts/ci_lint_ratchet.py --tool format
  python scripts/ci_lint_ratchet.py --tool all
  python scripts/ci_lint_ratchet.py --tool ruff --update
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

BASELINE = Path("config/ci_lint_baseline.json")
RUFF_COUNT_RE = re.compile(r"Found\s+(\d+)\s+error")
MYPY_COUNT_RE = re.compile(r"Found\s+(\d+)\s+error")
FORMAT_COUNT_RE = re.compile(r"(\d+)\s+files?\s+would be reformatted")

TOOLS = ("ruff", "mypy", "format")
BASELINE_KEYS = {
    "ruff": "ruff_errors",
    "mypy": "mypy_errors",
    "format": "format_files",
}


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


def run_ruff() -> int:
    p = _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "src",
            "tests",
            "config",
            "scripts",
            "--output-format=concise",
        ]
    )
    output = p.stdout + p.stderr
    m = RUFF_COUNT_RE.search(output)
    if m:
        return int(m.group(1))
    # 0 件のとき ruff は "All checks passed!" を返す
    if "All checks passed" in output:
        return 0
    raise RuntimeError(f"ruff の出力からエラー数を取得できませんでした:\n{output[-2000:]}")


def run_mypy() -> int:
    p = _run([sys.executable, "-m", "mypy", "src"])
    output = p.stdout + p.stderr
    if "Success: no issues found" in output:
        return 0
    m = MYPY_COUNT_RE.search(output)
    if m:
        return int(m.group(1))
    raise RuntimeError(
        "mypy の出力からエラー数を取得できませんでした"
        f"（終了コード {p.returncode}）:\n{output[-2000:]}"
    )


def run_format() -> int:
    p = _run([sys.executable, "-m", "ruff", "format", "--check", "src"])
    output = p.stdout + p.stderr
    m = FORMAT_COUNT_RE.search(output)
    if m:
        return int(m.group(1))
    if "already formatted" in output or p.returncode == 0:
        return 0
    raise RuntimeError(f"ruff format の出力から件数を取得できませんでした:\n{output[-2000:]}")


RUNNERS = {"ruff": run_ruff, "mypy": run_mypy, "format": run_format}


def _load_baseline() -> dict[str, int]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _save_baseline(data: dict[str, int]) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def check_tool(tool: str, *, update: bool) -> int:
    actual = RUNNERS[tool]()
    data = _load_baseline()
    key = BASELINE_KEYS[tool]

    if update:
        data[key] = actual
        _save_baseline(data)
        print(f"{tool}: baseline updated: {actual}")
        return 0

    if key not in data:
        # 初回導入時はベースラインを記録して通す（次回以降から ratchet が効く）
        data[key] = actual
        _save_baseline(data)
        print(f"{tool}: baseline was missing; recorded {actual}")
        return 0

    base = int(data[key])
    print(f"{tool}: actual={actual} baseline={base}")
    if actual > base:
        print(
            f"FAIL: {tool} の件数がベースラインより {actual - base} 件増加した。"
            " 意図した増加なら `--update` でベースラインを更新すること。",
            file=sys.stderr,
        )
        return 1
    if actual < base:
        data[key] = actual
        _save_baseline(data)
        print(f"GOOD: {base - actual} 件減少。ベースラインを下げた。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tool",
        choices=(*TOOLS, "all"),
        default="ruff",
        help="ratchet 対象（既定: ruff）",
    )
    ap.add_argument("--update", action="store_true", help="ベースラインを書き換える")
    args = ap.parse_args()

    tools = TOOLS if args.tool == "all" else (args.tool,)
    failures = 0
    for tool in tools:
        failures += check_tool(tool, update=args.update)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
