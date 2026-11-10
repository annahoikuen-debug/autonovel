#!/usr/bin/env python3
"""PLAN_S1 P4: 伏線 LLM 第 4 投票の shadow 一致率分析 CLI。

``ENABLE_FORESHADOW_LLM_VOTE=shadow`` で記録された
``logs/foreshadow_vote_shadow.jsonl`` を集計し、LLM 票と本線判定の一致率および
metadata 自己申告の過大申告率を算出する (PLAN_S1 §5-2)。

**過大申告率が有意でなければ mainline 化 (R3-④) は行わない** (コスト対効果)。

使い方:
  python -m scripts.analyze_foreshadow_vote_agreement [--log <path>] [--json]

出力 (人間可読):
  - 総判定数 / 一致率 / LLM アクション別件数
  - metadata 過大申告率 (metadata=resolved かつ LLM=unmentioned の割合)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.engine.foreshadowing.vote_shadow import DEFAULT_SHADOW_PATH, analyze_shadow_log

# mainline 化の目安 (PLAN_S1 §5-5)
AGREEMENT_TARGET = 0.70


def main(argv: list[str] | None = None) -> int:
    """CLI エントリポイント。終了コードを返す (分析失敗は 0 / 閾値未達は 2)。"""
    parser = argparse.ArgumentParser(
        prog="analyze_foreshadow_vote_agreement",
        description="伏線 LLM 第 4 投票の shadow 一致率を集計する",
    )
    parser.add_argument("--log", "-l", default=None, help="shadow JSONL のパス (既定: logs/foreshadow_vote_shadow.jsonl)")
    parser.add_argument("--json", action="store_true", help="JSON で出力する")
    parser.add_argument(
        "--agreement-target",
        type=float,
        default=AGREEMENT_TARGET,
        help=f"mainline 化の目安一致率 (既定: {AGREEMENT_TARGET})",
    )
    args = parser.parse_args(argv)

    log_path = Path(args.log) if args.log else DEFAULT_SHADOW_PATH
    result = analyze_shadow_log(log_path)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"shadow log: {result['path']}")
    print(f"  総判定数           : {result['total']}")
    print(f"  一致率             : {result['agreement_rate']:.2%} ({result['agreements']}/{result['total']})")
    print(f"  metadata 過大申告率: {result['metadata_over_report_rate']:.2%} ({result['metadata_over_reports']} 件)")
    actions = result.get("llm_action_counts") or {}
    if actions:
        summary = ", ".join(f"{name}={count}" for name, count in sorted(actions.items()))
        print(f"  LLM アクション分布 : {summary}")

    if result["total"] == 0:
        print("\n[NOTE] shadow 記録がありません。ENABLE_FORESHADOW_LLM_VOTE=shadow で運用してください。")
        return 0

    if result["agreement_rate"] >= args.agreement_target:
        print(f"\n✅ 一致率が目安 ({args.agreement_target:.0%}) を満たします。mainline 化を検討してください (R3-④)。")
        return 0
    print(
        f"\n⚠️ 一致率が目安 ({args.agreement_target:.0%}) に未達です。"
        "mainline 化は見送り、shadow 記録を継続してください。"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
