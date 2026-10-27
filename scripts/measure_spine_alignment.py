#!/usr/bin/env python
"""STORY_SPINE 導入の効果測定（親提案 §8 の K1-K3）。

既存書籍（Book × Plot）を STORY_SPINE のパターンに照らして検証し、
- K1: 構成充足度（必須ビートが genre 位置に存在した割合）
- K2: 中点反転の相対位置の散らばり
- K3: クライマックス位置の散らばり
を**実測**して JSON で出力する。

重要な原則（PLAN_T6 の教訓）:
- **推測値をハードコードしない。** ここに出る数値はすべて DB から計算した値。
- DB が無い/壊れている環境でも **0件で正常終了**する（計測で本番を落とさない）。
- 2回走らせても出力が一致すること（実測であることの証明）。

使い方:
    python scripts/measure_spine_alignment.py
    python scripts/measure_spine_alignment.py --json
    python scripts/measure_spine_alignment.py --json --pattern exile_rise
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_PATTERNS = ("exile_rise", "detective_mystery", "slow_life", "healing_care")


def _load_books(pattern_keys: tuple[str, ...]) -> list[dict]:
    """既存書籍を読み込む。DB が使えないときは空リストを返す（クラッシュさせない）。"""
    try:
        from src.backend.database.models import Plot
        from src.core.container import AppContainer
        from sqlalchemy import select
        from src.backend.database.uow import UnitOfWork
    except Exception as exc:  # import 自体ができない環境
        print(f"[warn] DB モジュールを読み込めませんでした: {exc}", file=sys.stderr)
        return [], False

    try:
        import asyncio

        async def _run() -> tuple[list[dict], bool]:
            out: list[dict] = []
            async with UnitOfWork(AppContainer.db()) as uow:
                if uow.session is None:
                    return out, False
                result = await uow.session.execute(
                    select(Plot).order_by(Plot.book_id, Plot.ep_num)
                )
                for row in result.scalars().all():
                    out.append(
                        {
                            "book_id": row.book_id,
                            "ep_num": row.ep_num,
                            "title": row.title or "",
                            "tension": int(row.tension or 0),
                        }
                    )
            return out, True

        return asyncio.run(_run())
    except Exception as exc:
        print(f"[warn] DB に接続できませんでした: {exc}", file=sys.stderr)
        return [], False


def _group_by_book(rows: list[dict]) -> dict[int, list[dict]]:
    books: dict[int, list[dict]] = {}
    for r in rows:
        books.setdefault(r["book_id"], []).append(r)
    for v in books.values():
        v.sort(key=lambda x: x["ep_num"])
    return books


def _phase(ep: int, total: int) -> float:
    """相対位置 0.0-1.0。structure_validator.assign_phases と同じ定義。"""
    if total <= 1:
        return 0.0
    return round((ep - 1) / (total - 1), 3)


def measure(pattern_keys: tuple[str, ...] = DEFAULT_PATTERNS) -> dict:
    """K1-K3 を実測して dict で返す。"""
    from src.services.structure_validator import validate

    rows, db_reachable = _load_books(pattern_keys)
    books = _group_by_book(rows)

    per_book: list[dict] = []
    for book_id, plots in sorted(books.items()):
        chapters = [
            {"chapter_number": p["ep_num"], "tension": p["tension"], "title": p["title"]}
            for p in plots
        ]
        total = len(chapters)
        if total == 0:
            continue

        alignments: list[float] = []
        for pk in pattern_keys:
            result = validate(chapters, pattern_key=pk)
            if "alignment" in result:
                alignments.append(float(result["alignment"]))

        # K2: 最も緊張が高い話の中点からの相対位置
        peak = max(chapters, key=lambda c: c["tension"])
        k3_climax = _phase(int(peak["chapter_number"]), total)

        # K2: 中点付近（0.4-0.6）の最高緊張話を探す
        mid_candidates = [c for c in chapters if 0.4 <= _phase(int(c["chapter_number"]), total) <= 0.6]
        k2_midpoint = (
            _phase(int(max(mid_candidates, key=lambda c: c["tension"])["chapter_number"]), total)
            if mid_candidates
            else None
        )

        per_book.append(
            {
                "book_id": book_id,
                "chapters": total,
                "k1_alignment": round(statistics.fmean(alignments), 3) if alignments else 0.0,
                "k2_midpoint": k2_midpoint,
                "k3_climax": k3_climax,
            }
        )

    mids = [b["k2_midpoint"] for b in per_book if b["k2_midpoint"] is not None]
    climaxes = [b["k3_climax"] for b in per_book]

    return {
        "patterns": list(pattern_keys),
        "db_reachable": db_reachable,
        "books": per_book,
        "book_count": len(per_book),
        "k1_alignment": round(statistics.fmean([b["k1_alignment"] for b in per_book]), 3)
        if per_book
        else None,
        "k2_midpoint": {
            "mean": round(statistics.fmean(mids), 3) if mids else None,
            "stdev": round(statistics.pstdev(mids), 3) if len(mids) > 1 else None,
            "in_band_rate": round(sum(1 for m in mids if 0.40 <= m <= 0.60) / len(mids), 3)
            if mids
            else None,
        },
        "k3_climax": {
            "mean": round(statistics.fmean(climaxes), 3) if climaxes else None,
            "stdev": round(statistics.pstdev(climaxes), 3) if len(climaxes) > 1 else None,
            "in_band_rate": round(sum(1 for c in climaxes if 0.75 <= c <= 0.92) / len(climaxes), 3)
            if climaxes
            else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="STORY_SPINE 効果測定")
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力")
    parser.add_argument("--pattern", action="append", help="测定するパターン（複数可）")
    args = parser.parse_args()

    patterns = tuple(args.pattern) if args.pattern else DEFAULT_PATTERNS
    payload = measure(patterns)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"書籍数: {payload['book_count']}")
        print(f"K1 構成充足度（平均）: {payload['k1_alignment']}")
        print(f"K2 中点反転: {payload['k2_midpoint']}")
        print(f"K3 クライマックス: {payload['k3_climax']}")
        if payload["book_count"] == 0:
            print("※ 対象書籍が0件です。DB を設定して再実行してください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
