#!/usr/bin/env python3
"""Shadow 一致率分析スクリプト (M6)。

shadow モードで記録された AuditRun レコードと、旧絶対ゲート (single モード)
のレコードを比較し、ペアワイズ判定と旧ゲートの一致率を算出する。

一致率が閾値 (既定 80%) を超えれば、gate.mode: percentile への切替を推奨する。

使い方:
  python scripts/analyze_shadow_agreement.py \
      --db-session <session> \
      [--agreement-threshold 0.8] \
      [--recommend]

環境変数:
  AUDIT_GATE_MODE: 切替後のモード (absolute / percentile)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("config/audit_calibration.yaml")


def analyze_shadow_agreement(
    rows_single: list[dict[str, Any]],
    rows_shadow: list[dict[str, Any]],
    *,
    agreement_threshold: float = 0.8,
) -> dict[str, Any]:
    """single モードと shadow モードのレコードを比較し、一致率を計算する。

    Args:
        rows_single: judge_mode="single" の AuditRun 辞書リスト
            (各要素: book_id, ep_num, final_score, is_passed, created_at)
        rows_shadow: judge_mode="shadow" の AuditRun 辞書リスト
        agreement_threshold: 一致率の閾値 (0-1)

    Returns:
        分析結果辞書
    """
    # (book_id, ep_num) でインデックス化
    single_index: dict[tuple[int, int], dict[str, Any]] = {}
    for r in rows_single:
        key = (int(r["book_id"]), int(r["ep_num"]))
        # 同じキーが複数ある場合は最新の created_at を採用
        if key not in single_index or r.get("created_at", "") > single_index[key].get(
            "created_at", ""
        ):
            single_index[key] = r

    shadow_index: dict[tuple[int, int], dict[str, Any]] = {}
    for r in rows_shadow:
        key = (int(r["book_id"]), int(r["ep_num"]))
        if key not in shadow_index or r.get("created_at", "") > shadow_index[key].get(
            "created_at", ""
        ):
            shadow_index[key] = r

    # 共通キーでペアリング
    common_keys = set(single_index.keys()) & set(shadow_index.keys())

    total = len(common_keys)
    agree_count = 0
    disagree_details: list[dict[str, Any]] = []

    for key in sorted(common_keys):
        s = single_index[key]
        sh = shadow_index[key]
        s_pass = bool(s.get("is_passed"))
        sh_pass = bool(sh.get("is_passed"))
        if s_pass == sh_pass:
            agree_count += 1
        else:
            disagree_details.append(
                {
                    "book_id": key[0],
                    "ep_num": key[1],
                    "single_is_passed": s_pass,
                    "single_score": s.get("final_score"),
                    "shadow_is_passed": sh_pass,
                    "shadow_score": sh.get("final_score"),
                }
            )

    agreement_rate = agree_count / total if total > 0 else 0.0
    recommend_switch = agreement_rate >= agreement_threshold and total > 0

    return {
        "total_pairs": total,
        "agree_count": agree_count,
        "disagree_count": total - agree_count,
        "agreement_rate": round(agreement_rate, 4),
        "agreement_threshold": agreement_threshold,
        "recommend_switch": recommend_switch,
        "recommended_mode": "percentile" if recommend_switch else "absolute",
        "disagree_details": disagree_details[:20],  # 最初の20件のみ
    }


def fetch_rows_from_audit_run(
    db_session: Any,
    *,
    judge_mode: str,
) -> list[dict[str, Any]]:
    """AuditRun テーブルから指定 judge_mode のレコードを取得する。"""
    try:
        AuditRun = (
            __import__(
                "src.infrastructure.database.models.audit_run", fromlist=["AuditRun"]
            ).AuditRun
        )
        rows = (
            db_session.query(AuditRun)
            .filter(AuditRun.judge_mode == judge_mode)
            .order_by(AuditRun.created_at.desc())
            .all()
        )
        return [
            {
                "book_id": r.book_id,
                "ep_num": r.ep_num,
                "final_score": r.final_score,
                "is_passed": r.is_passed,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    except Exception:  # noqa: BLE001 - DB 未接続時は空リスト
        return []


def update_yaml_mode(mode: str) -> None:
    """config/audit_calibration.yaml の gate.mode を更新する。"""
    import yaml

    if not CONFIG_PATH.exists():
        print(f"[WARN] 設定ファイルが見つかりません: {CONFIG_PATH}", file=sys.stderr)
        return

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    config.setdefault("gate", {})["mode"] = mode
    config["gate"]["mode_switched_at"] = (
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    )

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)

    print(f"[OK] yaml 更新: gate.mode = {mode}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shadow 一致率分析")
    parser.add_argument(
        "--db-session",
        dest="db_session",
        default=None,
        help="SQLAlchemy セッションオブジェクト",
    )
    parser.add_argument(
        "--agreement-threshold",
        type=float,
        default=0.8,
        help="一致率の閾値 (既定: 0.8)",
    )
    parser.add_argument(
        "--recommend",
        action="store_true",
        help="一致率が閾値を超えたら yaml の gate.mode を percentile に更新",
    )
    parser.add_argument(
        "--single-rows",
        dest="single_rows",
        default=None,
        help="テスト用: single モードの JSON ファイルパス",
    )
    parser.add_argument(
        "--shadow-rows",
        dest="shadow_rows",
        default=None,
        help="テスト用: shadow モードの JSON ファイルパス",
    )
    args = parser.parse_args(argv)

    if args.single_rows is not None and args.shadow_rows is not None:
        import json as _json

        with open(args.single_rows, encoding="utf-8") as f:
            rows_single = _json.load(f)
        with open(args.shadow_rows, encoding="utf-8") as f:
            rows_shadow = _json.load(f)
    elif args.db_session is not None:
        rows_single = fetch_rows_from_audit_run(args.db_session, judge_mode="single")
        rows_shadow = fetch_rows_from_audit_run(args.db_session, judge_mode="shadow")
    else:
        print(
            "[ERROR] --single-rows/--shadow-rows または --db-session を指定してください",
            file=sys.stderr,
        )
        return 1

    result = analyze_shadow_agreement(
        rows_single, rows_shadow, agreement_threshold=args.agreement_threshold
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.recommend and result["recommend_switch"]:
        update_yaml_mode("percentile")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
