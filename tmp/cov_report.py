"""coverage.json を集計してパッケージ別 / ファイル別の不足排行を出力する補助スクリプト。"""
from __future__ import annotations

import collections
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "cov_baseline.json"
top = int(sys.argv[2]) if len(sys.argv) > 2 else 40
data = json.load(open(path, encoding="utf-8"))

groups: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
rows = []
for p, v in data["files"].items():
    norm = p.replace("\\", "/")
    s = v["summary"]
    stmt, cov = s["num_statements"], s["covered_lines"]
    groups["/".join(norm.split("/")[:2])][0] += stmt
    groups["/".join(norm.split("/")[:2])][1] += cov
    rows.append((stmt - cov, 100 * cov / stmt if stmt else 100.0, stmt, norm))

rows.sort(reverse=True)
tot = sum(v[0] for v in groups.values())
miss = sum(v[0] - v[1] for v in groups.values())

print("== package ==")
print("%-36s %7s %7s %7s" % ("package", "stmts", "miss", "cov%"))
for k, (n, c) in sorted(groups.items(), key=lambda kv: kv[1][0] - kv[1][1], reverse=True):
    if n == 0:
        continue
    print("%-36s %7d %7d %7.1f" % (k, n, n - c, 100 * c / n))
print("%-36s %7d %7d %7.1f" % ("TOTAL", tot, miss, 100 * (tot - miss) / tot))

print("\n== worst files (by missing statements) ==")
for m, pc, stmt, norm in rows[:top]:
    print("%7.1f%% %6d miss %6d stmts  %s" % (pc, m, stmt, norm))
