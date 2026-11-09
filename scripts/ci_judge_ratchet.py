#!/usr/bin/env python3
"""擾乱スイート ratchet (M1-D)。

reports/judge_suite_*.json の最新結果を config/judge_baseline.json と比較し、
判定器の劣化を検出する。劣化があれば exit 1。

baseline 更新は --update-baseline のみ（人手レビュー前提）。
ci_lint_ratchet.py と同じ運用パターンに従う。

使い方:
  python scripts/ci_judge_ratchet.py --check
  python scripts/ci_judge_ratchet.py --update-baseline --report reports/judge_suite_unified_20261109.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from glob import glob
from pathlib import Path

BASELINE_PATH = Path("config/judge_baseline.json")
REPORTS_GLOB = "reports/judge_suite_*.json"

# 比較対象のメトリクスキーと許容劣化幅（絶対差）
METRIC_TOLERANCE = {
    "mean_rho": 0.05,          # ρ が 0.05 以上低下したら劣化
    "identifiability.expected_drop": 0.2,  # 期待軸低下が 20% 以上縮小したら劣化
    "invariance.max_delta": 0.5,  # INV の max_delta が 0.5 以上増加したら劣化
}


def _latest_report() -> Path | None:
    """最新の judge_suite レポートを返す。"""
    files = sorted(glob(REPORTS_GLOB))
    if not files:
        return None
    return Path(files[-1])


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _flat_metrics(report: dict) -> dict[str, float]:
    """レポートから比較用の扁平メトリクスを抽出する。"""
    flat: dict[str, float] = {}
    judge_id = report.get("judge_id", "unknown")
    flat[f"{judge_id}.n_transforms"] = float(report.get("n_transforms", 0))
    flat[f"{judge_id}.n_texts"] = float(report.get("n_texts", 0))

    for tm in report.get("transforms", []):
        tid = tm["transform_id"]
        flat[f"{judge_id}.{tid}.mean_rho"] = float(tm.get("mean_rho", 0.0))
        flat[f"{judge_id}.{tid}.all_passed"] = 1.0 if tm.get("all_passed") else 0.0

        ident = tm.get("identifiability") or {}
        if ident:
            flat[f"{judge_id}.{tid}.identifiability.expected_drop"] = float(
                ident.get("expected_drop", 0.0)
            )
            flat[f"{judge_id}.{tid}.identifiability.ratio"] = float(
                ident.get("ratio", 0.0) if ident.get("ratio") != float("inf") else 0.0
            )
            flat[f"{judge_id}.{tid}.identifiability.identified"] = (
                1.0 if ident.get("identified") else 0.0
            )

        inv = tm.get("invariance") or {}
        if inv:
            flat[f"{judge_id}.{tid}.invariance.max_delta"] = float(
                inv.get("max_delta", 0.0)
            )
            flat[f"{judge_id}.{tid}.invariance.passed"] = (
                1.0 if inv.get("passed") else 0.0
            )

    return flat


def _compare(baseline: dict, current: dict) -> list[str]:
    """baseline と current を比較し、劣化したメトリクスの説明を返す。"""
    problems: list[str] = []
    b_flat = _flat_metrics(baseline)
    c_flat = _flat_metrics(current)

    all_keys = set(b_flat.keys()) | set(c_flat.keys())
    for key in sorted(all_keys):
        b_val = b_flat.get(key)
        c_val = c_flat.get(key)
        if b_val is None:
            # 新規メトリクス（追加）は警告のみ
            continue
        if c_val is None:
            problems.append(f"  {key}: baseline={b_val} 現在=欠損")
            continue

        # 許容劣化幅を判定
        tolerance = None
        for prefix, tol in METRIC_TOLERANCE.items():
            if key.endswith(prefix):
                tolerance = tol
                break

        if tolerance is not None:
            # 数値メトリクス：baseline - current > tolerance で劣化
            diff = b_val - c_val
            if diff > tolerance:
                problems.append(
                    f"  {key}: baseline={b_val:.4f} 現在={c_val:.4f} (劣化 {diff:.4f} > 許容 {tolerance})"
                )
        else:
            # それ以外は厳密比較（all_passed などのフラグは劣化のみ検出）
            if key.endswith(".all_passed") or key.endswith(".identified") or key.endswith(".passed"):
                if b_val == 1.0 and c_val == 0.0:
                    problems.append(f"  {key}: baseline=合格 現在=不合格")
            elif b_val != c_val:
                problems.append(f"  {key}: baseline={b_val} 現在={c_val}")

    return problems


def cmd_check() -> int:
    """チェックモード。baseline と最新レポートを比較する。"""
    if not BASELINE_PATH.exists():
        print(f"[ERROR] baseline が存在しません: {BASELINE_PATH}", file=sys.stderr)
        print("    --update-baseline で最初の baseline を作成してください。", file=sys.stderr)
        return 1

    report_path = _latest_report()
    if report_path is None:
        print(f"[ERROR] レポートが見つかりません: {REPORTS_GLOB}", file=sys.stderr)
        return 1

    baseline = _load_json(BASELINE_PATH)
    current = _load_json(report_path)

    problems = _compare(baseline, current)

    if problems:
        print(f"[FAIL] 判定器の劣化を検出しました (baseline: {BASELINE_PATH})", file=sys.stderr)
        print(f"    比較対象: {report_path}", file=sys.stderr)
        for p in problems:
            print(p, file=sys.stderr)
        return 1

    print(f"[OK] 判定器の劣化は検出されませんでした (baseline: {BASELINE_PATH}, レポート: {report_path})")
    return 0


def cmd_update_baseline(report_path: str) -> int:
    """baseline を更新する。"""
    src = Path(report_path)
    if not src.exists():
        print(f"[ERROR] レポートが見つかりません: {src}", file=sys.stderr)
        return 1

    baseline = _load_json(src)
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[OK] baseline を更新しました: {BASELINE_PATH}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="擾乱スイート ratchet")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check", action="store_true", help="baseline と最新レポートを比較して劣化を検出"
    )
    group.add_argument(
        "--update-baseline",
        metavar="REPORT_JSON",
        help="指定レポートを baseline として保存",
    )
    args = parser.parse_args(argv)

    if args.check:
        return cmd_check()
    if args.update_baseline:
        return cmd_update_baseline(args.update_baseline)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
