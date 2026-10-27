#!/bin/bash
# run_tests.sh - テスト実行スクリプト

set -e

# このスクリプトは scripts/runners/ にあり、テスト対象はリポジトリルート配下の
# src/ tests/ である。CWD を固定していないため、どのディレクトリから実行しても
# pytest / ruff / mypy がルート相対パスを解決できるよう、リポジトリルートへ移動する。
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== AutoNovel Test Suite ==="

# 依存チェック
echo "Checking dependencies..."
pip list | grep -E "(pytest|ruff|mypy|prometheus-client|pyyaml)" > /dev/null || {
    echo "Missing dependencies. Install with: pip install -e \".[dev]\""
    exit 1
}

# リンター
echo "Running ruff..."
ruff check src tests

# 型チェック（緩め）
echo "Running mypy..."
mypy src --ignore-missing-imports

# フォーマットチェック
# 旧実装は `black --check` を呼んでいたが、このプロジェクトは black ではなく
# ruff format を使用しており（Makefile の format-check ターゲット参照）、
# black は requirements.txt / pyproject.toml のどこにも宣言されていないため
# `black: command not found` + `set -e` で pytest に到達する前に中断していた。
echo "Running ruff format check..."
ruff format --check src tests config scripts

# テスト実行
echo "Running unit tests..."
pytest tests/unit -v --tb=short

echo "Running integration tests..."
pytest tests/integration -v --tb=short

echo "=== All checks passed ==="