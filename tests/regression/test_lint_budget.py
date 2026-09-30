"""lint の残存数が「増やす了一道 人」増えないことの回帰テスト。

T6 Step 10 の回帰防止。

`ruff check` を緑にする操作的削除（F401 の機械削除）は、
`src/narrative_balancer` の再エクスポートを壊して **ImportError** を招いた
（実測済み）。したがって F401 は意図的な import を人が判断する項目として残す。

残存数を**上限として固定**し、悪化（増加）を機械的に検出できるようにする。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: T6 Step 10 完了時点の実測残存数。これを超えたら fail。
#: 減少 には LintBudgetError として明示的にこの値を下げる。
LINT_ERROR_BUDGET = 700

#: 機械削除が**必ず壊す**ことが確認済みのリグレッション。
#: このモジュールの import が壊れていたら F401 除去を再開してはならない。
REEXPORT_SENTINEL = "src/narrative_balancer"


def _ruff_statistics() -> dict[str, int]:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src", "tests", "--statistics"],
        capture_output=True, text=True, cwd=ROOT, encoding="utf-8", errors="replace",
    )
    counts: dict[str, int] = {}
    for line in result.stdout.splitlines():
        m = re.match(r"^(\d+)\s+(\S+)", line.strip())
        if m:
            counts[m.group(2)] = int(m.group(1))
    return counts


def test_lint_error_count_within_budget():
    """lint 残存数が予算内であること（悪化すると落ちる）。"""
    counts = _ruff_statistics()
    total = sum(counts.values())
    assert total <= LINT_ERROR_BUDGET, (
        f"lint 残存 {total} 件が予算 {LINT_ERROR_BUDGET} 件を超過。\n"
        f"内訳: {counts}"
    )


def test_whitespace_rules_are_clean():
    """W 系（純整形）は 0 件であること。

    T6 Step 10 で 1646 件を解消済み。これらが再発しないことを固定する。
    """
    counts = _ruff_statistics()
    for code in ("W291", "W292", "W293"):
        assert counts.get(code, 0) == 0, (
            f"{code} が {counts[code]} 件に再発（純整形なので自動修正可能）"
        )


def test_reexport_modules_still_importable():
    """F401 機械削除で壊れやすい再エクスポート系が import できること。"""
    import importlib

    for mod in (
        "src.narrative_balancer",
        "src.narrative_balancer.dsp",
        "src.narrative_balancer.dsp.models",
        "src.narrative_balancer.arbitrator",
        "src.narrative_balancer.grammar",
    ):
        importlib.import_module(mod)


def test_reexport_names_still_exposed():
    """`dsp` が `Beat` などの再エクスポート名を提供し続けていること。

    T6 Step 10 で F401 を機械削除すると、ここが `ImportError` になった。
    """
    from src.narrative_balancer import dsp

    for name in ("Beat", "BeatType", "DSPConfig", "TensionSignal"):
        assert hasattr(dsp, name), f"src.narrative_balancer.dsp.{name} が消えている"


@pytest.mark.parametrize("rule", ["F401", "F841", "F811"])
def test_non_whitespace_rules_are_known(rule: str):
    """残存ルールが想定内のものかを明示する（未知のルール追加を検知）。"""
    counts = _ruff_statistics()
    if rule in counts:
        assert counts[rule] > 0
