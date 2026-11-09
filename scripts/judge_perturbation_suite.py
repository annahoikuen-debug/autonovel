#!/usr/bin/env python3
"""擾乱スイート CLI (M1-D)。

被験判定器を指定して擾乱スイートを実行し、レポートを JSON で出力する。

使い方:
  python scripts/judge_perturbation_suite.py \
      --corpus storage/judge_corpus/*.txt \
      --judge unified \
      --model gemini-3.5-flash-lite \
      --prompt-version v1 \
      --out reports/judge_suite_unified_$(date +%Y%m%d).json \
      --corpus-limit 20

オプション:
  --corpus:      対象テキストファイルの glob パターン（複数指定可）
  --judge:       判定器種別 (unified | mock)  既定: mock
  --model:       使用モデル名（レポートに記録のみ）
  --prompt-version: プロンプトバージョン（レポートに記録のみ）
  --out:         出力 JSON パス（指定がない場合は stdout）
  --corpus-limit: コーパス上限数（スモークテスト用）
  --rho-threshold: Spearman ρ の合格閾値（既定 0.8）
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

from src.audit.perturbation.suite import JudgeSuite, run_judge_suite


def _read_corpus(patterns: list[str], limit: int | None = None) -> list[str]:
    """glob パターンからテキストファイルを読み込み、コーパスを返す。"""
    files: list[str] = []
    for pat in patterns:
        files.extend(sorted(glob.glob(pat)))
    corpus: list[str] = []
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                corpus.append(f.read())
        except OSError as e:
            print(f"[WARN] 読み込みスキップ: {fp} ({e})", file=sys.stderr)
    if limit is not None:
        corpus = corpus[:limit]
    return corpus


def _make_judge(kind: str):
    """判定器 callable を生成する。"""
    if kind == "mock":
        def mock_judge(text: str) -> dict[str, float]:
            return {
                "hook": min(100.0, len(text) * 0.1),
                "overall": min(100.0, len(text) * 0.08),
                "emotional": 50.0,
                "character_consistency": 70.0,
            }
        return mock_judge
    if kind == "unified":
        # 遅延インポート（LLM プロバイダ未設定時でもインポートエラーを避ける）
        import asyncio

        from src.agents.specialists.unified_auditor import UnifiedAuditor

        auditor = UnifiedAuditor()

        def unified_judge(text: str) -> dict[str, float]:
            try:
                report = asyncio.run(auditor.audit(text))
                return {
                    "hook": report.qualitative.hook_score,
                    "emotional": report.qualitative.emotional_score,
                    "character_consistency": report.qualitative.character_consistency,
                    "overall": report.qualitative.overall_score,
                }
            except Exception as e:  # noqa: BLE001 - 判定器失敗は空スコア
                print(f"[WARN] 判定器失敗: {e}", file=sys.stderr)
                return {}
        return unified_judge
    raise ValueError(f"不明な判定器種別: {kind}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="擾乱スイート CLI")
    parser.add_argument(
        "--corpus",
        action="append",
        required=True,
        help="対象テキストファイルの glob パターン（複数指定可）",
    )
    parser.add_argument(
        "--judge",
        choices=["mock", "unified"],
        default="mock",
        help="判定器種別 (既定: mock)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="使用モデル名（レポートに記録のみ）",
    )
    parser.add_argument(
        "--prompt-version",
        default="1.0",
        help="プロンプトバージョン（既定: 1.0）",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="出力 JSON パス（指定がない場合は stdout）",
    )
    parser.add_argument(
        "--corpus-limit",
        type=int,
        default=None,
        help="コーパス上限数（スモークテスト用）",
    )
    parser.add_argument(
        "--rho-threshold",
        type=float,
        default=0.8,
        help="Spearman ρ の合格閾値（既定: 0.8）",
    )
    args = parser.parse_args(argv)

    corpus = _read_corpus(args.corpus, limit=args.corpus_limit)
    if not corpus:
        print("[ERROR] コーパスが空です", file=sys.stderr)
        return 1

    judge = _make_judge(args.judge)
    report = run_judge_suite(
        judge=judge,
        corpus=corpus,
        judge_id=args.judge,
        model_name=args.model,
        prompt_version=args.prompt_version,
        rho_threshold=args.rho_threshold,
    )

    out_json = report.to_json()
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out_json, encoding="utf-8")
        print(f"[OK] レポートを出力しました: {out_path}", file=sys.stderr)
    else:
        print(out_json)

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
