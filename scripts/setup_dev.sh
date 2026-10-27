#!/bin/bash
# setup_dev.sh - 開発環境セットアップ

set -e

# 必ずリポジトリルートで実行する。`pip install -e .` はカレントディレクトリを
# パッケージルートとみなすため、scripts/ から実行すると失敗する
# （旧実装に CWD ガードが無く `bash scripts/setup_dev.sh` で落ちていた）。
# scripts/check_env.py の PROJECT_ROOT と同じ考え方。
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
echo "Project root: $PROJECT_ROOT"

echo "=== AutoNovel Development Setup ==="

# Python バージョンチェック
python_version=$(python3 --version | cut -d' ' -f2)
echo "Python version: $python_version"

# 仮想環境作成（存在しない場合）
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# 仮想環境アクティベート
source .venv/bin/activate

# pip アップグレード
pip install --upgrade pip

# 依存インストール
echo "Installing dependencies..."
pip install -e ".[dev]"

# マイグレーション実行
# alembic.ini はリポジトリルートにしかないうえ、その script_location は
# `src/backend/alembic` とルート相対で指定されている。`cd src/backend` してから
# 呼ぶと "ERROR: Can't locate a configuration file" で失敗する。
echo "Running database migrations..."
alembic upgrade head

echo "=== Setup complete ==="
echo "Activate virtual environment with: source .venv/bin/activate"
echo "Run tests with: ./scripts/runners/run_tests.sh"