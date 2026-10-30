"""4層アーキテクチャの依存境界チェック（ratchet）。

目標アーキテクチャ（内側 → 外側）:

    src.domain  →  src.application  →  src.infrastructure  →  src.interfaces

このスクリプトは 2 種類の契約を検証する。

  [HARD]    契約1「純粋な内側依存」:
            内側レイヤーが外側レイヤーを import しない。
            （現状 0 違反。baseline を持たず、増加したら即 fail する恒久ルール。）

  [RATCHET] 契約2「旧来の巨大モノリスへの依存」:
            正規レイヤーが src.backend / src.services / src.agents という
            旧レイアウトの巨大モノリスを import しない。
            現状の違反数を config/layer_boundaries_baseline.json に記録し、
            「縮小のみ許可」する（既存の ci_lint_ratchet.py と同じ方式）。

外部依存なし（標準ライブラリ ast のみ）で数秒で実行できる。
既存の ci_lint_ratchet.py との違いは「件数ベースの ratchet」ではなく
「レイヤー境界の契約」を対象にする点。

使い方:
  python scripts/check_layer_boundaries.py                   # チェック（契約1は恒久 / 契約2は ratchet）
  python scripts/check_layer_boundaries.py --update-baseline # 契約2のベースラインを再記録
  python scripts/check_layer_boundaries.py --report          # 違反ファイルの一覧（移行 TODO 用）
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

# 目標 4 層（内側 → 外側）。インデックスが小さいほど内側。
CANONICAL_LAYERS: list[str] = ["domain", "application", "infrastructure", "interfaces"]

# 契約2 の対象となる旧来の巨大モノリス（今後、4 層へ分割・統合していく）。
LEGACY_MONOLITHS: tuple[str, ...] = ("src.backend", "src.services", "src.agents")

BASELINE_PATH = Path("config/layer_boundaries_baseline.json")
SRC_ROOT = Path("src")


def _layer_dir(layer: str) -> Path:
    return SRC_ROOT / layer


def _iter_py_files(layer: str):
    base = _layer_dir(layer)
    if not base.exists():
        return
    for path in sorted(base.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _absolute_src_prefixes(path: Path) -> set[str]:
    """ファイルが import する `src.<top>` のトップレベル接頭辞の集合を返す。

    相対 import (level>0) は同一レイヤー内とみなして無視する。
    `src.backend.config` → `src.backend` のように第2セグメントまで正規化する。
    """
    prefixes: set[str] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return prefixes
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                prefixes.update(_prefix(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # 相対 import は同一レイヤー内
            if node.module:
                prefixes.update(_prefix(node.module))
    return prefixes


def _prefix(module: str) -> set[str]:
    """`src.backend.config` → {"src.backend"} のように正規化する。"""
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "src":
        return {f"src.{parts[1]}"}
    return set()


def _collect(layer: str, forbidden: set[str]) -> dict[str, list[str]]:
    """レイヤー内で forbidden 接頭辞を import する {ファイル: [違反 import...]} を返す。"""
    violations: dict[str, list[str]] = {}
    for path in _iter_py_files(layer):
        hits = sorted(p for p in _absolute_src_prefixes(path) if p in forbidden)
        if hits:
            violations[str(path)] = hits
    return violations


def _contract1_violations() -> dict[str, dict[str, list[str]]]:
    """契約1: 内側レイヤーが外側の正規レイヤーを import していないか（恒久ルール）。"""
    result: dict[str, dict[str, list[str]]] = {}
    for i, layer in enumerate(CANONICAL_LAYERS):
        outer = CANONICAL_LAYERS[i + 1 :]
        if not outer:
            break
        forbidden = {f"src.{o}" for o in outer}
        v = _collect(layer, forbidden)
        if v:
            result[layer] = v
    return result


def _contract2_counts() -> dict[str, int]:
    """契約2: 各正規レイヤーが旧巨大モノリスを import する件数（ratchet 対象）。"""
    forbidden = set(LEGACY_MONOLITHS)
    counts: dict[str, int] = {}
    for layer in CANONICAL_LAYERS:
        counts[layer] = sum(len(hits) for hits in _collect(layer, forbidden).values())
    return counts


def _contract2_details() -> dict[str, dict[str, list[str]]]:
    """--report 用: 契約2 の違反を {レイヤー: {ファイル: [import...]}} で返す。"""
    forbidden = set(LEGACY_MONOLITHS)
    out: dict[str, dict[str, list[str]]] = {}
    for layer in CANONICAL_LAYERS:
        v = _collect(layer, forbidden)
        if v:
            out[layer] = v
    return out


def _load_baseline() -> dict:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _save_baseline(data: dict) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_check(*, update_baseline: bool, report: bool) -> int:
    failures = 0

    # ---- 契約1: 純粋な内側依存（恒久ルール・baseline なし） ----
    c1 = _contract1_violations()
    if c1:
        failures += 1
        print("契約1 [HARD] 違反: 内側レイヤーが外側の正規レイヤーを import しています")
        for layer, files in c1.items():
            for f, hits in files.items():
                print(f"  {f} -> {', '.join(hits)}")
        print("  -> 依存を反転させ、内側レイヤーから外側への import を排除してください。\n")
    else:
        print("契約1 [HARD] OK: 正規レイヤー間は純粋な内側依存（domain→app→infra→interfaces）\n")

    # ---- 契約2: 旧巨大モノリスへの依存（ratchet） ----
    actual = _contract2_counts()
    total = sum(actual.values())
    if report:
        print(f"契約2 [RATCHET] 違反の内訳（合計 {total} 件 / 移行 TODO として扱う）:")
        details = _contract2_details()
        for layer, files in details.items():
            print(f"  src/{layer}: {actual[layer]} 件")
            for f, hits in sorted(files.items()):
                print(f"    {f} -> {', '.join(hits)}")
        return 1 if failures else 0

    baseline = _load_baseline()
    base_map: dict[str, int] = baseline.get("legacy_monolith_imports", {})

    if update_baseline or not base_map:
        _save_baseline({**baseline, "legacy_monolith_imports": actual})
        verb = "updated" if update_baseline else "was missing; recorded"
        print(f"契約2 [RATCHET] baseline {verb}: {actual} (total={total})")
        return 1 if failures else 0

    regressed: list[str] = []
    improved: list[str] = []
    for layer in CANONICAL_LAYERS:
        a = actual[layer]
        b = int(base_map.get(layer, 0))
        if a > b:
            regressed.append(f"  src/{layer}: {a} > baseline {b} (+{a - b})")
        elif a < b:
            improved.append(f"  src/{layer}: {b} -> {a} ({b - a} 件減少)")
            base_map[layer] = a

    if regressed:
        failures += 1
        print("契約2 [RATCHET] FAIL: 旧巨大モノリスへの依存がベースラインより増加した")
        for line in regressed:
            print(line)
        print("  -> 意図した増加でなければ依存を排除すること。意図なら --update-baseline。")
    elif improved:
        _save_baseline({**baseline, "legacy_monolith_imports": base_map})
        print("契約2 [RATCHET] OK（縮小）:")
        for line in improved:
            print(line)
    else:
        print(f"契約2 [RATCHET] OK: baseline と同等（合計 {total} 件、縮小待ち）")

    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="4層アーキテクチャの依存境界チェック")
    ap.add_argument("--update-baseline", action="store_true", help="契約2のベースラインを再記録する")
    ap.add_argument("--report", action="store_true", help="違反の内訳（移行TODO）を表示する")
    args = ap.parse_args()
    return run_check(update_baseline=args.update_baseline, report=args.report)


if __name__ == "__main__":
    raise SystemExit(main())
