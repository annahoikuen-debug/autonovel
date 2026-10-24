"""mypy の「劣化のみ検出」ratchet。

``ruff`` の lint ratchet (:mod:`scripts.ci_lint_ratchet.py`) と同様の運用手順だが、
「総エラー数」だけでなく **ファイルごとのエラー数** も併せて固定する。

単に総数だけを見ると、あるファイルで 10 件直したついでに別のファイルで
5 件持ち込んでも総数は減るので検出できない。ファイル単位の上限を設けることで
「新規/既存コードに型エラーを持ち込まない」を強制し、既存債権は凍結する。

ルール:
* ベースラインに載っていないファイル → エラー 0 を要求
* 載っているファイル → ベースライン以下の件数のみ許容
* 総数もベースライン以下であること

改善したら総数が減るのでスクリプトはベースラインを自動で書き下げる
(改善は自動で追跡され、後から戻すと FAIL する)。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

BASELINE = Path("config/ci_mypy_baseline.json")

# mypy の1行出力: `path/to/file.py:12:5: error: message  [code]`
# `--no-error-summary` を付けているので要約行は現れない想定。
LINE_RE = re.compile(r"^(?P<path>[^:\n]+\.py):(?P<line>\d+):(?:(?P<col>\d+):)?\s*(?P<kind>error|note):")


def run_mypy() -> "tuple[Counter, int]":
    """mypy を実行し (ファイル別エラー数, 総数) を返す。"""
    p = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "src",
            "--ignore-missing-imports",
            "--no-error-summary",
            "--show-error-codes",
        ],
        capture_output=True,
        text=True,
    )
    counts: Counter = Counter()
    total = 0
    for raw in (p.stdout or "").splitlines():
        m = LINE_RE.match(raw.strip())
        if not m or m.group("kind") != "error":
            continue
        path = m.group("path").replace("\\", "/")
        # 相対化 (CI では Linux、ローカルでは Windows でも同じキーにする)
        for prefix in ("./",):
            if path.startswith(prefix):
                path = path[len(prefix) :]
        counts[path] += 1
        total += 1
    return counts, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="ベースラインを書き換える")
    args = ap.parse_args()

    actual, total = run_mypy()

    if args.update:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {"mypy_errors_total": total, "mypy_errors_per_file": dict(sorted(actual.items()))},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"baseline updated: total={total} files={len(actual)}")
        return 0

    if not BASELINE.exists():
        print(f"FAIL: ベースラインがありません: {BASELINE} (--update で生成してください)", file=sys.stderr)
        return 1

    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    base_files: dict[str, int] = base.get("mypy_errors_per_file", {})
    base_total = int(base.get("mypy_errors_total", sum(base_files.values())))

    print(f"mypy errors: actual={total} baseline={base_total} files={len(actual)}")

    regressions: list[str] = []
    for path in sorted(actual):
        limit = base_files.get(path, 0)
        if actual[path] > limit:
            regressions.append(f"  {path}: {actual[path]} errors (baseline {limit})")
    if total > base_total:
        regressions.append(f"  total: {total} (baseline {base_total})")

    if regressions:
        print("FAIL: mypy エラーがベースラインを超えたファイル:", file=sys.stderr)
        print("\n".join(regressions), file=sys.stderr)
        return 1

    if total < base_total:
        BASELINE.write_text(
            json.dumps(
                {"mypy_errors_total": total, "mypy_errors_per_file": dict(sorted(actual.items()))},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"GOOD: {base_total - total} 件減少。ベースラインを下げた。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
