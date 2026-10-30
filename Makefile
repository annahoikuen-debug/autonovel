# AutoNovel Makefile - 一般的な開発タスクのエイリアス。
# Windows でも GNU Make (Git for Windows 同梱等) で実行可能。

PYTHON ?= python3

.PHONY: help install dev test lint lint-layers typecheck openapi frontend-test frontend-lint run dev-up dev-down prod-up prod-down clean verify test-unit test-integration test-contract test-perf test-migration format-check check-migrations

help:  ## 利用可能ターゲット一覧を表示
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install:  ## バックエンド依存をインストール
	$(PYTHON) -m pip install -e .[dev]

dev: install  ## 開発用インストール (バック + フロント)
	cd frontend && npm install

test:  ## pytest を実行 (バックエンド)
	$(PYTHON) -m pytest -q --tb=short -m "not integration and not perf and not slow"

lint:  ## ruff チェック
	$(PYTHON) -m ruff check src tests config scripts

lint-layers:  ## 4層アーキテクチャの依存境界チェック (内側依存は恒久 / レガシー接続は ratchet)
	$(PYTHON) scripts/check_layer_boundaries.py

format-check:  ## ruff format チェック (line-length 120)
	$(PYTHON) -m ruff format --check src tests config scripts

typecheck:  ## mypy (strict 化は将来フェーズ)
	$(PYTHON) -m mypy src --ignore-missing-imports

openapi:  ## OpenAPI 仕様を docs/openapi.json へ生成
	$(PYTHON) scripts/generate_openapi.py --output docs/openapi.json

frontend-test:  ## フロントエンド vitest
	cd frontend && npm run test:ci

frontend-lint:  ## フロントエンド eslint + typecheck
	cd frontend && npm run lint && npm run typecheck

run:  ## 開発サーバ (backend only) を起動
	$(PYTHON) -m uvicorn src.backend.server:app --reload --port 8200

dev-up:  ## docker compose 開発環境を起動
	docker compose up --build

dev-down:  ## docker compose 開発環境を停止
	docker compose down

prod-up:  ## docker compose 本番環境を起動
	docker compose -f docker-compose.prod.yml up -d --build

prod-down:  ## docker compose 本番環境を停止
	docker compose -f docker-compose.prod.yml down

clean:  ## 生成物・キャッシュを削除
	-rm -rf .pytest_cache .ruff_cache .mypy_cache
	-rm -f autonovel.db huey.db test_migration.db a.db test.db docs/openapi.json
	-find . -type d -name __pycache__ -prune -exec rm -rf {} +

test-unit:  ## ユニットテスト (coverage gate 60% で開始、段階引き上げ)
	$(PYTHON) -m pytest tests/unit -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=60

test-integration:  ## 統合テスト (PG+Redis サービス必須)
	$(PYTHON) -m pytest tests/integration -v --tb=short

test-contract:  ## 契約テスト (OpenAPI スナップショット・Pydantic スキーマ)
	$(PYTHON) -m pytest tests/contract -v --tb=short

test-perf:  ## パフォーマンステスト (benchmarks.json ベースライン比較)
	$(PYTHON) -m pytest tests/perf -v --tb=short --benchmark-only --benchmark-autosave

# alembic.ini はリポジトリルートにしか無く、script_location = src/backend/alembic も
# ルート相対なので、必ずルート（make の起動ディレクトリ）から実行する。
test-migration:  ## alembic 整合性チェック (alembic check + 往復)
	alembic check && alembic upgrade head && alembic downgrade -1 && alembic upgrade head

check-migrations:  ## マイグレーション往復検証スクリプトを実行
	$(PYTHON) scripts/check_migrations.py

verify: lint lint-layers format-check typecheck test-unit test-contract test-migration  ## PR 前のフル検証 (CI と同じ順序)
	@echo "All checks passed."

coverage:  ## カバレッジ計測・レポート生成
	$(PYTHON) -m pytest --cov=src --cov-report=term-missing --cov-report=html
	cd frontend && npm run test:ci -- --coverage

frontend-coverage:  ## フロントエンドのカバレッジのみ
	cd frontend && npm run test:ci -- --coverage

backend-coverage:  ## バックエンドのカバレッジのみ
	$(PYTHON) -m pytest --cov=src --cov-report=term-missing --cov-report=html
