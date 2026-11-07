"""Phase R0: shim 使用統計の観測基盤 (SHIM_REMOVAL_PLAN)。

src/ と tests/ 内で旧パス（shim 経由の参照）がどれだけ残っているかを
CI ログにレポートする。Phase R2（参照解消）の進捗測定に使用する。

削除バッチの条件は「当該カテゴリの旧パス参照数 == 0」であるため、
本テストの出力が削除判断の基礎データになる。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config" / "shim_registry.json"

registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
SHIMS: list[str] = registry["shims"]


def _count_references(old_mod_dot: str) -> int:
    """src/ と tests/ 内で旧モジュール名（ドット記法）を参照するファイル数を数える。"""
    count = 0
    for base in ["src", "tests"]:
        for py_file in (ROOT / base).rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if old_mod_dot in content:
                count += 1
    return count


def test_report_shim_usage_stats():
    """各 shim の旧パス参照数を CI ログにレポートする（観測用・常に緑）。"""
    report_lines: list[str] = []
    total_referenced = 0
    unreferenced = 0

    for shim_path in SHIMS:
        if not (ROOT / shim_path).exists():
            continue
        old_mod = shim_path.replace("/", ".").replace(".py", "")
        n = _count_references(old_mod)
        if n > 0:
            total_referenced += 1
            report_lines.append(f"  [参照あり {n:>3}件] {shim_path}")
        else:
            unreferenced += 1

    report = (
        f"\n=== Shim 使用統計 (Phase R0 観測) ===\n"
        f"shim 総数: {len(SHIMS)} / 参照あり: {total_referenced} / 参照なし: {unreferenced}\n"
        + "\n".join(report_lines)
        + "\n=== 統計ここまで ===\n"
    )
    # 常に緑。CI ログでの観測が目的。
    print(report)

    # 軽い健全性チェックのみ: registry と src/services の実在整合
    assert len(SHIMS) > 0, "shim registry が空"
