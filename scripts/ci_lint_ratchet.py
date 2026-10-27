"""静的解析の「劣化のみ検出」ratchet。

ベースライン JSON に記録されたエラー数を超えたら fail する。
ベースラインを下げることで改善を追えるが、
「全エラー 0 化」を目的とはしない (PLAN_H1 §9 で対象外と明記)。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

BASELINE = Path("config/ci_lint_baseline.json")
COUNT_RE = re.compile(r"Found\s+(\d+)\s+error")


def run_ruff() -> int:
    p = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src", "tests", "config", "scripts",
         "--output-format=concise"],
        capture_output=True, text=True,
    )
    m = COUNT_RE.search(p.stdout + p.stderr)
    return int(m.group(1)) if m else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="ベースラインを書き換える")
    args = ap.parse_args()

    actual = run_ruff()
    if args.update:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps({"ruff_errors": actual}, indent=2), encoding="utf-8")
        print(f"baseline updated: {actual}")
        return 0

    base = json.loads(BASELINE.read_text(encoding="utf-8"))["ruff_errors"]
    print(f"ruff errors: actual={actual} baseline={base}")
    if actual > base:
        print(f"FAIL: ruff エラー数がベースラインより {actual - base} 件増加した", file=sys.stderr)
        return 1
    if actual < base:
        BASELINE.write_text(json.dumps({"ruff_errors": actual}, indent=2), encoding="utf-8")
        print(f"GOOD: {base - actual} 件減少。ベースラインを下げた。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
