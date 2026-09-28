"""coverage.json から任意のパREFIX集合ごとの未カバー数を集計するスライス分割용スクリプト。"""
from __future__ import annotations

import json
import sys

data = json.load(open("cov_baseline.json", encoding="utf-8"))
prefixes = sys.argv[1:]
rows = []
for pfx in prefixes:
    pfx = pfx.replace("\\", "/").rstrip("/")
    n = c = files = 0
    for p, v in data["files"].items():
        p = p.replace("\\", "/")
        if p == pfx or p.startswith(pfx + "/"):
            s = v["summary"]
            n += s["num_statements"]
            c += s["covered_lines"]
            files += 1
    rows.append((n - c, pfx, files, n, c))

rows.sort(reverse=True)
print("%-42s %6s %6s %6s %6s %6s" % ("prefix", "files", "stmts", "miss", "cov%", "miss/d100"))
for miss, pfx, files, n, c in rows:
    print(
        "%-42s %6d %6d %6d %6.1f %6d"
        % (pfx, files, n, miss, 100 * c / n if n else 0, miss // 100)
    )
print("\nTOTAL MISS %d" % sum(r[0] for r in rows))
