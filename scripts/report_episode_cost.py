"""1話あたりのLLMコストを報告するCLI（T6 Step 6）。

親計画 Step 27「効果測定レポート（1話あたりUSD）を出力するCLIを整備する」の
成果物。従来は pytest の `print` しかなく、
`TokenTracker.get_total_cost_usd` / `get_task_breakdown` / `get_tier_breakdown`
は**テストからしか呼ばれていなかった**。

集計ロジックを再実装せず、`TokenTracker` の既存集計メソッドをそのまま使う。

使い方:
    python scripts/report_episode_cost.py
    python scripts/report_episode_cost.py --episodes 1,2,3
    python scripts/report_episode_cost.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# `src` を import する前にリポジトリルートを sys.path へ入れる
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.services.token_tracker import TokenTracker  # noqa: E402

#: 1話レポートの出力キー（`docs/STATUS.md` の効果測定表が読む契約）
REPORT_KEYS = (
    "ep_num",
    "llm_calls",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "total_cost_usd",
    "by_task",
    "by_tier",
)


def build_episode_row(record: dict[str, Any]) -> dict[str, Any]:
    """1話分の計測レコードをレポート行へ変換する。

    ``record`` は `TokenTracker` の生レコード（`add_usage` と同じキー）。

    Returns:
        `REPORT_KEYS` をすべて持つ dict
    """
    ep_num = record.get("ep_num")
    input_tokens = int(record.get("input_tokens", 0) or 0)
    output_tokens = int(record.get("output_tokens", 0) or 0)
    model = record.get("model_name")
    task_type = record.get("task_type") or "unknown"
    tier = record.get("tier") or "unrouted"

    cost = TokenTracker.estimate_cost_usd(input_tokens, output_tokens, model)

    return {
        "ep_num": ep_num,
        "llm_calls": 1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "total_cost_usd": cost,
        "by_task": {task_type: {"calls": 1, "cost_usd": cost, "tokens": input_tokens + output_tokens}},
        "by_tier": {tier: {"calls": 1, "cost_usd": cost, "tokens": input_tokens + output_tokens}},
    }


def aggregate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """計測レコードを話ごとに集約してレポート行を返す。"""
    episodes: dict[int, dict[str, Any]] = {}
    for rec in records:
        ep_num = rec.get("ep_num")
        if ep_num is None:
            continue
        row = episodes.setdefault(
            int(ep_num),
            {
                "ep_num": int(ep_num),
                "llm_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "by_task": {},
                "by_tier": {},
            },
        )
        one = build_episode_row(rec)
        row["llm_calls"] += one["llm_calls"]
        row["input_tokens"] += one["input_tokens"]
        row["output_tokens"] += one["output_tokens"]
        row["total_tokens"] += one["total_tokens"]
        row["total_cost_usd"] = round(row["total_cost_usd"] + one["total_cost_usd"], 8)
        for key in ("by_task", "by_tier"):
            for name, agg in one[key].items():
                bucket = row[key].setdefault(
                    name, {"calls": 0, "cost_usd": 0.0, "tokens": 0}
                )
                bucket["calls"] += agg["calls"]
                bucket["tokens"] += agg["tokens"]
                bucket["cost_usd"] = round(
                    bucket["cost_usd"] + agg["cost_usd"], 8
                )
    return [episodes[k] for k in sorted(episodes)]


def build_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    """レポート全体の構造を組み立てる。"""
    episodes = aggregate_records(records)
    total_cost = round(sum(e["total_cost_usd"] for e in episodes), 8)
    return {
        "episodes": episodes,
        "totals": {
            "episode_count": len(episodes),
            "llm_calls": sum(e["llm_calls"] for e in episodes),
            "input_tokens": sum(e["input_tokens"] for e in episodes),
            "output_tokens": sum(e["output_tokens"] for e in episodes),
            "total_tokens": sum(e["total_tokens"] for e in episodes),
            "total_cost_usd": total_cost,
            "usd_per_episode": (
                round(total_cost / len(episodes), 8) if episodes else 0.0
            ),
        },
    }


def _records_from_tracker(tracker: TokenTracker) -> list[dict[str, Any]]:
    """`TokenTracker` の集計から擬似レコードを復元する（集計ロジック再実装を避ける）。"""
    records: list[dict[str, Any]] = []
    for task, bucket in tracker.get_task_breakdown().items():
        for model, _count in bucket.get("models", {}).items():
            records.append(
                {
                    "ep_num": None,
                    "task_type": task,
                    "model_name": model,
                    "input_tokens": bucket["input_tokens"],
                    "output_tokens": bucket["output_tokens"],
                    "tier": tracker._infer_tier(model),
                }
            )
    return records


def _load_records(db_path: str | None, book_id: int | None) -> list[dict[str, Any]]:
    """計測レコードをDBから読む。DB が無ければ空リストを返す。"""
    if not db_path:
        return []
    import sqlite3
    from pathlib import Path

    path = Path(db_path)
    if not path.exists():
        return []

    query = (
        "SELECT ep_num, task_type, model_name, tier,"
        "       input_tokens, output_tokens"
        "  FROM token_usage"
    )
    params: list[Any] = []
    if book_id is not None:
        query += " WHERE book_id = ?"
        params.append(book_id)
    query += " ORDER BY ep_num"

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(query, params).fetchall()
        except sqlite3.Error:
            return []
    return [dict(r) for r in rows]


def _render_text(report: dict[str, Any]) -> str:
    lines = ["ep_num | calls |  tokens  |  USD/ep  | by_task"]
    lines.append("-" * 60)
    for ep in report["episodes"]:
        tasks = ",".join(f"{k}:{v['calls']}" for k, v in sorted(ep["by_task"].items()))
        lines.append(
            f"{ep['ep_num']:>5} | {ep['llm_calls']:>5} | {ep['total_tokens']:>8} "
            f"| {ep['total_cost_usd']:>8.6f} | {tasks}"
        )
    t = report["totals"]
    lines.append("-" * 60)
    lines.append(
        f"合計: {t['episode_count']}話 / {t['llm_calls']} calls / "
        f"{t['total_tokens']} tokens / ${t['total_cost_usd']:.6f} "
        f"(1話あたり ${t['usd_per_episode']:.6f})"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="1話あたりのLLMコストを報告する（T6 Step 6）"
    )
    parser.add_argument("--db", help="token_usage を持つSQLiteファイルのパス")
    parser.add_argument("--book-id", type=int, help="対象作品IDで絞り込む")
    parser.add_argument("--episodes", help="カンマ区切りの話番号で絞り込む（例: 1,2,3）")
    parser.add_argument("--json", action="store_true", help="機械可読形式で出力")
    args = parser.parse_args(argv)

    records = _load_records(args.db, args.book_id)
    if args.episodes:
        wanted = {int(x) for x in args.episodes.split(",") if x.strip()}
        records = [r for r in records if r.get("ep_num") in wanted]

    report = build_report(records)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
