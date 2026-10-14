"""カバレッジ検証用ヘルパー。

pytest-cov と coverage.py のデータを用いて、ブランチ/ステートメントカバレッジを
プログラマティックに検証するユーティリティを提供する。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _load_coverage_data(coverage_file: Path | None = None) -> dict[str, Any]:
    """カバレッジデータを読み込む。

    Args:
        coverage_file: カバレッジJSONファイルのパス。Noneの場合は標準の場所を探す。

    Returns:
        coverage.py の JSON レポート形式の辞書。
    """
    if coverage_file is None:
        # 一般的な場所を探索
        candidates = [
            Path("coverage.json"),
            Path(".coverage"),
            Path("htmlcov/coverage.json"),
        ]
        for c in candidates:
            if c.exists():
                coverage_file = c
                break

    if coverage_file is None or not coverage_file.exists():
        # coverage json を生成
        try:
            subprocess.run(
                [sys.executable, "-m", "coverage", "json", "-o", "coverage.json"],
                check=True,
                capture_output=True,
            )
            coverage_file = Path("coverage.json")
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise FileNotFoundError("Coverage data not found. Run tests with --cov first.")

    if coverage_file.suffix == ".json":
        with open(coverage_file, encoding="utf-8") as f:
            return json.load(f)

    # .coverage バイナリファイルの場合は coverage json コマンドで変換
    try:
        subprocess.run(
            [sys.executable, "-m", "coverage", "json", "-o", "coverage.json"],
            check=True,
            capture_output=True,
        )
        with open("coverage.json", encoding="utf-8") as f:
            return json.load(f)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(f"Failed to load coverage data: {e}") from e


def get_uncovered_lines(module_path: str, coverage_file: Path | None = None) -> list[int]:
    """指定モジュールの未カバー行番号リストを返す。

    Args:
        module_path: モジュールのファイルパス (例: "src/services/llm_adapter.py")
        coverage_file: カバレッジJSONファイルのパス (省略可)

    Returns:
        未カバー行番号のリスト。カバレッジデータになければ空リスト。
    """
    data = _load_coverage_data(coverage_file)

    # coverage.json の files キーから対象を探す
    files = data.get("files", {})
    # パスの正規化 (相対パス、POSIX区切り)
    normalized_path = module_path.replace("\\", "/")

    # 完全一致を試みる
    file_data = files.get(normalized_path)
    if file_data is None:
        # ファイル名のみで部分一致を試みる
        target_name = Path(normalized_path).name
        for path, fdata in files.items():
            if Path(path).name == target_name:
                file_data = fdata
                break

    if file_data is None:
        return []

    missing_lines = file_data.get("missing_lines", [])
    return [int(line) for line in missing_lines]


def _get_coverage_pct(module_path: str, coverage_file: Path | None, branch: bool) -> float:
    """指定モジュールのカバレッジ率(%)を取得する内部関数。"""
    data = _load_coverage_data(coverage_file)

    files = data.get("files", {})
    normalized_path = module_path.replace("\\", "/")

    file_data = files.get(normalized_path)
    if file_data is None:
        target_name = Path(normalized_path).name
        for path, fdata in files.items():
            if Path(path).name == target_name:
                file_data = fdata
                break

    if file_data is None:
        return 0.0

    summary = file_data.get("summary", {})
    if branch:
        return float(summary.get("percent_covered_branches", 0.0))
    return float(summary.get("percent_covered", 0.0))


def assert_branch_covered(module_path: str, min_pct: float = 80.0, coverage_file: Path | None = None) -> None:
    """ブランチカバレッジが閾値以上か検証する。

    Args:
        module_path: 対象モジュールのファイルパス
        min_pct: 最小カバレッジ率 (%)
        coverage_file: カバレッジJSONファイルのパス (省略可)

    Raises:
        AssertionError: カバレッジが閾値未満の場合
    """
    pct = _get_coverage_pct(module_path, coverage_file, branch=True)
    if pct < min_pct:
        uncovered = get_uncovered_lines(module_path, coverage_file)
        raise AssertionError(
            f"Branch coverage for {module_path} is {pct:.2f}% (expected >= {min_pct}%). "
            f"Uncovered lines: {uncovered[:50]}"
        )


def assert_stmt_covered(module_path: str, min_pct: float = 80.0, coverage_file: Path | None = None) -> None:
    """ステートメントカバレッジが閾値以上か検証する。

    Args:
        module_path: 対象モジュールのファイルパス
        min_pct: 最小カバレッジ率 (%)
        coverage_file: カバレッジJSONファイルのパス (省略可)

    Raises:
        AssertionError: カバレッジが閾値未満の場合
    """
    pct = _get_coverage_pct(module_path, coverage_file, branch=False)
    if pct < min_pct:
        uncovered = get_uncovered_lines(module_path, coverage_file)
        raise AssertionError(
            f"Statement coverage for {module_path} is {pct:.2f}% (expected >= {min_pct}%). "
            f"Uncovered lines: {uncovered[:50]}"
        )
