"""テスト収集件数の後退を検出する。

conftest.py の pytest_ignore_collect / pytest_collection_modifyitems 等で
テストが無言で収集対象外になるのを防ぐため、pytest --collect-only の
収集件数をベースラインと比較し、減少していたら fail する。

Usage:
  python scripts/check_test_collection.py           # CI 用（減少で exit 1）
  python scripts/check_test_collection.py --update  # ベースラインを更新
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "config" / "test_collection_baseline.json"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


def _collect_count() -> int:
    """pytest --collect-only の収集件数を返す。"""
    p = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ]
    )
    output = p.stdout + p.stderr

    # pytest バージョンによって出力形式が異なる:
    #  - "collected 10703 items" (古い pytest)
    #  - "9766 tests collected" (pytest 9.x)
    m = re.search(r"(\d+)\s+tests?\s+collected", output)
    if m:
        return int(m.group(1))
    m = re.search(r"collected\s+(\d+)\s+items?", output)
    if m:
        return int(m.group(1))
    if p.returncode != 0:
        raise RuntimeError(
            f"pytest --collect-only が終了コード {p.returncode} で失敗しました。"
            f" collection error が発生している可能性があります:\n{output[-2000:]}"
        )
    raise RuntimeError(f"pytest --collect-only の出力から収集件数を取得できませんでした:\n{output[-2000:]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="収集件数ベースラインを更新")
    args = ap.parse_args()

    try:
        actual = _collect_count()
    except RuntimeError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    if args.update:
        data = {"collected": actual}
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"test collection baseline updated: {actual}")
        return 0

    if not BASELINE.exists():
        data = {"collected": actual}
        BASELINE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"test collection baseline was missing; recorded {actual}")
        return 0

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    base = int(baseline.get("collected", 0))
    print(f"test collection: actual={actual} baseline={base}")
    if actual < base:
        print(
            f"FAIL: テスト収集件数がベースラインより {base - actual} 件減少した。"
            " conftest.py の収集除外ロジックやテストファイルの削除・移動を確認すること。",
            file=sys.stderr,
        )
        return 1
    if actual > base:
        # 増加は問題ない（新規テスト追加）。ベースラインは更新しない（減少のみ検知）
        print(f"GOOD: {actual - base} 件増加（ベースラインは維持）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
