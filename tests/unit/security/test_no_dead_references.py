"""削除済みモジュールへの残存参照（死んだ参照）を検出する回帰テスト。

PLAN_J1 W5: `src/backend/security/credit_guard.py` を削除したが、
参照元が残っていると import 時に ModuleNotFoundError になる。
本テストは「参照ゼロ」を機械的に固定し、将来モジュールを削除する際の
safety net として機能する。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# 削除済みモジュール（`src/backend/security/` 配下から除去されたもの）。
REMOVED_MODULES: tuple[str, ...] = ("credit_guard",)

SEARCH_ROOTS: tuple[str, ...] = ("src", "tests")


def _scan_for_references() -> list[str]:
    """src/ と tests/ 配下の .py から削除済みモジュールへの参照を列挙する。"""
    self_path = Path(__file__).resolve()
    hits: list[str] = []
    for root_name in SEARCH_ROOTS:
        base = ROOT / root_name
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if path.resolve() == self_path:
                continue  # 本テスト自身は needle を含むため除外
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for name in REMOVED_MODULES:
                if name in text:
                    hits.append(f"{path.relative_to(ROOT)} -> {name}")
    return sorted(hits)


def test_no_references_to_removed_modules() -> None:
    """削除済みモジュール(credit_guard)への残存参照が無いこと。"""
    hits = _scan_for_references()
    assert not hits, (
        "削除済みモジュールへの残存参照が見つかります（import が壊れます）:\n"
        + "\n".join(hits)
    )
