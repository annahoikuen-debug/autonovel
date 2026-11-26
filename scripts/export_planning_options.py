"""planning_options の実レスポンスを JSON で書き出す（FE テストの唯一の fixture 源）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backend.routers.misc import get_planning_options

DEFAULT_OUT = Path("frontend/tests/fixtures/planning_options.snapshot.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--check",
        action="store_true",
        help="書き出さずに既存スナップショットと一致するかだけ確認する",
    )
    args = ap.parse_args()

    payload = asyncio.run(get_planning_options())
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not args.out.exists():
            print(f"[fail] スナップショットが無い: {args.out}")
            return 1
        if args.out.read_text(encoding="utf-8") != text:
            print(f"[fail] スナップショットが Reality と不一致。`{args.out}` を再生成せよ")
            # CI では生成環境差（依存バージョン・実行環境）の切り分けに必要なため
            # 不一致の差分を表示する（先頭 60 行。巨大化を避けるため制限付き）。
            import difflib

            current = args.out.read_text(encoding="utf-8").splitlines()
            reality = text.splitlines()
            diff = list(
                difflib.unified_diff(
                    current, reality, fromfile="snapshot", tofile="reality", n=1, lineterm=""
                )
            )
            for line in diff[:60]:
                print(line)
            if len(diff) > 60:
                print(f"... (diff 全 {len(diff)} 行中 60 行のみ表示)")
            return 1
        print("[ok] スナップショットは最新")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"[ok] {args.out} を書き出した")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
