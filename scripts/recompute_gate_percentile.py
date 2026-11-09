#!/usr/bin/env python3
"""ゲートパーセンタイル再計算スクリプト (M5-C)。

AuditRun テーブルから直近 N 件の final_score を取得し、
パーセンタイル (既定 P30) を算出して stdout に出力する。
週次 cron などで実行し、結果を AUDIT_PERCENTILE_THRESHOLD 環境変数
または config/audit_calibration.yaml に反映する想定。

使い方:
  python scripts/recompute_gate_percentile.py \
      --window 200 --percentile 30 \
      --db-session <session> \
      [--update-yaml]

環境変数:
  AUDIT_PERCENTILE_THRESHOLD: 算出結果をここで上書きする (calibration_store が読む)
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("config/audit_calibration.yaml")


def _percentile(sorted_values: list[float], p: float) -> float:
    """ソート済みリストから第 p パーセンタイルを算出 (線形補間)。"""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    d0 = sorted_values[int(f)] * (c - k)
    d1 = sorted_values[int(c)] * (k - f)
    return d0 + d1


def compute_percentile_threshold(
    scores: list[float],
    *,
    window: int = 200,
    percentile: float = 30.0,
) -> dict[str, Any]:
    """スコアリストからパーセンタイル閾値を計算する。"""
    if not scores:
        return {
            "n": 0,
            "window": window,
            "percentile": percentile,
            "threshold": None,
            "min": None,
            "max": None,
            "mean": None,
        }

    # 直近 window 件のみ使用 (scores は既に時系列順で並んでいる前提)
    recent = scores[-window:] if len(scores) > window else scores[:]
    sorted_scores = sorted(recent)
    threshold = _percentile(sorted_scores, percentile)

    return {
        "n": len(recent),
        "window": window,
        "percentile": percentile,
        "threshold": round(threshold, 2),
        "min": round(min(sorted_scores), 2),
        "max": round(max(sorted_scores), 2),
        "mean": round(statistics.mean(sorted_scores), 2),
    }


def fetch_scores_from_audit_run(
    db_session: Any,
    *,
    window: int = 200,
) -> list[float]:
    """AuditRun テーブルから final_score を時系列順に取得する。"""
    try:
        rows = (
            db_session.query(__import__("src.infrastructure.database.models.audit_run", fromlist=["AuditRun"]).AuditRun)
            .order_by(__import__("src.infrastructure.database.models.audit_run", fromlist=["AuditRun"]).AuditRun.created_at.asc())
            .limit(window)
            .all()
        )
        return [float(r.final_score) for r in rows if r.final_score is not None]
    except Exception:  # noqa: BLE001 - DB 未接続時は空リスト
        return []


def update_yaml_threshold(threshold: float) -> None:
    """config/audit_calibration.yaml の gate.percentile.last_computed を更新する。"""
    import yaml

    if not CONFIG_PATH.exists():
        print(f"[WARN] 設定ファイルが見つかりません: {CONFIG_PATH}", file=sys.stderr)
        return

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    config.setdefault("gate", {}).setdefault("percentile", {})["last_computed"] = round(threshold, 2)
    config["gate"]["percentile"]["last_computed_at"] = (
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    )

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)

    print(f"[OK] yaml 更新: gate.percentile.last_computed = {threshold:.2f}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ゲートパーセンタイル再計算")
    parser.add_argument("--window", type=int, default=200, help="直近 N 件 (既定: 200)")
    parser.add_argument(
        "--percentile", type=float, default=30.0, help="パーセンタイル (既定: 30)"
    )
    parser.add_argument(
        "--db-session",
        dest="db_session",
        default=None,
        help="SQLAlchemy セッションオブジェクト (Python から呼び出す場合)",
    )
    parser.add_argument(
        "--update-yaml",
        action="store_true",
        help="計算結果を config/audit_calibration.yaml に書き込む",
    )
    parser.add_argument(
        "--scores",
        dest="scores",
        default=None,
        help="テスト用: カンマ区切りのスコアリスト (DB なしで動作確認)",
    )
    args = parser.parse_args(argv)

    if args.scores is not None:
        scores = [float(s) for s in args.scores.split(",")]
    elif args.db_session is not None:
        scores = fetch_scores_from_audit_run(args.db_session, window=args.window)
    else:
        print("[ERROR] --scores または --db-session を指定してください", file=sys.stderr)
        return 1

    result = compute_percentile_threshold(
        scores, window=args.window, percentile=args.percentile
    )

    if result["threshold"] is None:
        print("[ERROR] スコアが空のため閾値を計算できません", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.update_yaml:
        update_yaml_threshold(result["threshold"])

    # 環境変数出力 (caller が source で読み込む想定)
    print(f"export AUDIT_PERCENTILE_THRESHOLD={result['threshold']}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
