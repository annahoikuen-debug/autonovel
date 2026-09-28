"""``python -X importtime`` の出力 (``logs/importtime*.txt``) を解析し、
指定モジュールを「どのトップレベル import 連鎖」が読み込んだかを突き止める。

使い方:
    python scripts/debug/analyze_importtime.py logs/importtime2.txt google.genai openai
"""

from __future__ import annotations

import sys
from pathlib import Path


def parse(path: Path) -> list[tuple[int, str, float, float]]:
    """(深さ, モジュール名, self_us, cumulative_us) のリストを返す。"""
    rows: list[tuple[int, str, float, float]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.startswith("import time:"):
            continue
        body = raw[len("import time:") :]
        left, _, name = body.partition("|")
        # name 側の " cumulative |  module" を分割する
        _junk, _, right = name.partition("|")
        module = right.strip()
        depth = (len(right) - len(right.lstrip())) // 3
        try:
            self_us = float(left.strip())
            cum_us = float(_junk.strip())
        except ValueError:
            continue
        rows.append((depth, module, self_us, cum_us))
    return rows


def find_chain(rows: list[tuple[int, str, float, float]], target: str) -> list[str] | None:
    """``target`` を読み込んだ import 連鎖（トップレベル → 末端）を返す。"""
    stack: list[str] = []
    for depth, module, _self_us, _cum_us in rows:
        del stack[depth:]
        if depth == 0:
            stack = [module]
        else:
            while len(stack) < depth:
                stack.append("?")
            stack.append(module)
        if module == target:
            return list(stack)
    return None


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = Path(argv[1])
    targets = argv[2:] or ["google.genai", "openai", "chromadb"]
    rows = parse(path)
    if not rows:
        print(f"no importtime rows parsed from {path}")
        return 1
    total = max((c for *_x, c in rows), default=0.0)
    print(f"{path}: {len(rows)} modules, total cumulative {total / 1e6:.1f}s")
    print("")
    for target in targets:
        chain = find_chain(rows, target)
        print(f"--- {target} ---")
        if chain is None:
            print("  NOT IMPORTED (lazy)")
        else:
            for i, mod in enumerate(chain):
                print(f"  {'  ' * i}{'-> ' if i else '   '}{mod}")
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
