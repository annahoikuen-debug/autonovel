"""coverage.json から指定ソースファイルの未カバー行番号を抽出して表示する補助スクリプト。

使い方:
    py tmp/missing_lines.py <cov_json> <src_path> [<src_path> ...]
    py tmp/missing_lines.py cov_baseline.json src/agents/audit.py
    py tmp/missing_lines.py cov_baseline.json --under 60        # 60%未満のファイルを列挙
    py tmp/missing_lines.py cov_baseline.json --dir src/agents   # ディレクトリ内のみ
"""
from __future__ import annotations

import json
import os
import sys


def norm(p: str) -> str:
    return p.replace("\\", "/")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    cov_path = args[0]
    targets = [a for a in args[1:] if not a.startswith("--")]
    flags = {a for a in args[1:] if a.startswith("--")}

    data = json.load(open(cov_path, encoding="utf-8"))
    files = {norm(p): v for p, v in data["files"].items()}

    if "--under" in flags:
        idx = args.index("--under")
        threshold = float(args[idx + 1])
        rows = []
        for p, v in files.items():
            s = v["summary"]
            pc = s["percent_covered"] if s["num_statements"] else 100.0
            if pc < threshold and s["num_statements"] > 0:
                rows.append((s["num_statements"] - s["covered_lines"], pc, s["num_statements"], p))
        rows.sort(reverse=True)
        for miss, pc, stmt, p in rows:
            print("%6.1f%% %5d miss %5d stmts  %s" % (pc, miss, stmt, p))
        print("\n%d files below %.0f%%" % (len(rows), threshold))
        return

    if "--dir" in flags:
        idx = args.index("--dir")
        prefix = norm(args[idx + 1]).rstrip("/") + "/"
        targets = sorted(p for p in files if p.startswith(prefix))
    else:
        targets = [norm(t) for t in targets]

    for t in targets:
        v = files.get(t)
        if v is None:
            cand = [p for p in files if p.endswith(t)]
            if not cand:
                print("!! not found: %s" % t)
                continue
            t = cand[0]
            v = files[t]
        s = v["summary"]
        missing = v["missing_lines"]
        print(
            "== %s  %.1f%%  %d/%d stmts  %d missing"
            % (t, s["percent_covered"], s["covered_lines"], s["num_statements"], len(missing))
        )
        if missing:
            print("   missing lines: " + ", ".join(str(x) for x in missing))
        print()


if __name__ == "__main__":
    main()
