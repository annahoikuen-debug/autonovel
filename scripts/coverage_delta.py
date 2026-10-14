#!/usr/bin/env python3
"""前回実行の .coverage と比較し、未カバー上位 N モジュールを JSON 出力する。

Usage:
    python scripts/coverage_delta.py --top 20 --format json
    python scripts/coverage_delta.py --top 10 --format table
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def load_coverage_json(coverage_file: Path) -> dict[str, Any]:
    """coverage.json を読み込む。存在しない場合は生成を試みる。"""
    if not coverage_file.exists():
        try:
            subprocess.run(
                [sys.executable, "-m", "coverage", "json", "-o", str(coverage_file)],
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(f"Failed to generate coverage.json: {e}") from e

    with open(coverage_file, encoding="utf-8") as f:
        return json.load(f)


def load_previous_coverage(coverage_data_file: Path) -> dict[str, Any] | None:
    """前回の .coverage データファイルからカバレッジ情報を抽出する。"""
    if not coverage_data_file.exists():
        return None

    try:
        # coverage.py のデータファイルを読み込み、JSON に変換
        import coverage

        cov = coverage.Coverage(data_file=str(coverage_data_file))
        cov.load()
        # 一時的に JSON に出力して読み込む
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            cov.json_report(outfile=str(tmp_path))
            with open(tmp_path, encoding="utf-8") as f:
                return json.load(f)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
    except Exception:
        return None


def get_uncovered_modules(coverage_data: dict[str, Any], min_stmts: int = 10) -> list[dict[str, Any]]:
    """未カバー率が高いモジュールを抽出する。

    Args:
        coverage_data: coverage.json のパース結果
        min_stmts: 対象とする最小ステートメント数 (これ未満は除外)

    Returns:
        未カバー率順にソートされたモジュール情報のリスト
    """
    files = coverage_data.get("files", {})
    results = []

    for path, file_data in files.items():
        summary = file_data.get("summary", {})
        num_statements = summary.get("num_statements", 0)
        if num_statements < min_stmts:
            continue

        percent_covered = summary.get("percent_covered", 0.0)
        missing_lines = file_data.get("missing_lines", [])

        results.append(
            {
                "path": path,
                "num_statements": num_statements,
                "missing_lines": missing_lines,
                "num_missing": len(missing_lines),
                "percent_covered": percent_covered,
                "percent_uncovered": 100.0 - percent_covered,
            }
        )

    # 未カバー率で降順ソート
    results.sort(key=lambda x: x["percent_uncovered"], reverse=True)
    return results


def compute_delta(current: dict[str, Any], previous: dict[str, Any] | None) -> list[dict[str, Any]]:
    """現在と前回のカバレッジ差分を計算する。"""
    if previous is None:
        return get_uncovered_modules(current)

    current_modules = {m["path"]: m for m in get_uncovered_modules(current)}
    previous_modules = {m["path"]: m for m in get_uncovered_modules(previous)}

    delta_results = []
    for path, curr in current_modules.items():
        prev = previous_modules.get(path)
        if prev is None:
            delta_results.append(
                {
                    "path": path,
                    "num_statements": curr["num_statements"],
                    "num_missing": curr["num_missing"],
                    "percent_covered": curr["percent_covered"],
                    "percent_uncovered": curr["percent_uncovered"],
                    "delta_uncovered": curr["num_missing"],
                    "status": "new",
                }
            )
        else:
            delta_uncovered = curr["num_missing"] - prev["num_missing"]
            delta_results.append(
                {
                    "path": path,
                    "num_statements": curr["num_statements"],
                    "num_missing": curr["num_missing"],
                    "percent_covered": curr["percent_covered"],
                    "percent_uncovered": curr["percent_uncovered"],
                    "delta_uncovered": delta_uncovered,
                    "status": "improved" if delta_uncovered < 0 else "worsened" if delta_uncovered > 0 else "unchanged",
                }
            )

    # delta_uncovered でソート (悪化したものから)
    delta_results.sort(key=lambda x: x["delta_uncovered"], reverse=True)
    return delta_results


def format_json(results: list[dict[str, Any]], top_n: int) -> str:
    """JSON 形式で出力する。"""
    return json.dumps(results[:top_n], indent=2, ensure_ascii=False)


def format_table(results: list[dict[str, Any]], top_n: int) -> str:
    """テーブル形式で出力する。"""
    lines = []
    header = f"{'Rank':>4}  {'Path':<60} {'Stmts':>6} {'Miss':>6} {'Cov%':>6} {'Uncov%':>7} {'Delta':>7} {'Status'}"
    lines.append(header)
    lines.append("-" * len(header))

    for i, r in enumerate(results[:top_n], 1):
        path = r["path"]
        if len(path) > 58:
            path = "..." + path[-55:]
        delta = r.get("delta_uncovered", 0)
        status = r.get("status", "")
        lines.append(
            f"{i:>4}  {path:<60} {r['num_statements']:>6} {r['num_missing']:>6} "
            f"{r['percent_covered']:>5.1f}% {r['percent_uncovered']:>6.1f}% {delta:>+7} {status}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare coverage with previous run and show top uncovered modules")
    parser.add_argument("--top", type=int, default=20, help="Number of top modules to show (default: 20)")
    parser.add_argument("--format", choices=["json", "table"], default="json", help="Output format (default: json)")
    parser.add_argument("--current", type=Path, default=Path("coverage.json"), help="Current coverage.json path")
    parser.add_argument("--previous", type=Path, default=Path(".coverage"), help="Previous .coverage data file path")
    parser.add_argument("--min-stmts", type=int, default=10, help="Minimum statements to consider (default: 10)")

    args = parser.parse_args()

    try:
        current_data = load_coverage_json(args.current)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    previous_data = load_previous_coverage(args.previous)

    delta_results = compute_delta(current_data, previous_data)

    if args.format == "json":
        output = format_json(delta_results, args.top)
    else:
        output = format_table(delta_results, args.top)

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())