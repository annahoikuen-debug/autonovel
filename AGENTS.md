# AGENTS.md — AutoNovel

OpenCode セッション向けのコンパクトな手順書。エージェントが知らないと間違いやすい、リポジトリ固有の情報のみを記載。汎用的なアドバイスは省く。

## スタックとエントリポイント

- **バックエンド**: FastAPI。実エントリポイントは `src/interfaces/api/app_factory.py`（`create_app`、`build_lifespan`、`build_wiring`）。`src/backend/server.py` は後方互換シムなので、新規コードは `app_factory` を直接インポートする。
- **ワーカー**: Huey。コンシューマエントリは `src.backend.tasks.huey.huey`。
- **フロントエンド**: React 18 + Vite、ディレクトリ `frontend/`、開発サーバポート `5173`。
- **4層アーキテクチャ**: `src/domain` → `src.application` → `src.infrastructure` → `src.interfaces`。内側レイヤーが外側レイヤーをインポートしない（`scripts/check_layer_boundaries.py` で恒久ゲート）。
- **テスト**: `tests/`。`pytest.ini` の `pythonpath = .` によりリポジトリルートが `sys.path` に入る。

## セットアップ

```bash
# バックエンド（Python 3.12+）
py -3.12 -m venv .venv
# Windows
.venv/Scripts/Activate.ps1
# macOS/Linux
source .venv/bin/activate
py -m pip install -e ".[dev,rag]"

# フロントエンド
cd frontend && npm install && cd ..
```

- `.env` を `.env.example` からコピーし、必要に応じて環境変数を調整。
- 認証は開発でも有効。`http://localhost:5173/register` でユーザー登録し、API リクエストには `Authorization: Bearer <token>` を付与（トークンなしは 401）。
- ローカル開発は SQLite + `HUEY_BACKEND=sqlite`（`DATABASE_URL=sqlite:///./autonovel.db`）。

## 起動 / 開発サーバ

Windows（公式、推奨）:
```powershell
scripts\start_local.ps1   # バックエンド :8200 + Huey ワーカー + フロントエンド :5173 を協調起動
scripts\stop_local.ps1    # 停止
scripts\doctor.ps1        # 起動に失敗したらまず実行（診断）
```

手動（3 つのターミナル）:
```powershell
$env:HUEY_BACKEND = "sqlite"
$env:DATABASE_URL = "sqlite:///./autonovel.db"
py -m uvicorn src.backend.server:app --reload --port 8200   # ターミナル 1
py -m huey.bin.huey_consumer src.backend.tasks.huey.huey     # ターミナル 2
cd frontend && npm run dev                                  # ターミナル 3 → :5173
```

Docker:
- 開発: `docker compose up --build`
- 本番: `docker compose -f docker-compose.prod.yml up -d --build`（`make prod-up` と同等）
- 本番では `CORS_ORIGINS=*` は起動エラーになる。実オリジンをカンマ区切りで指定。

## 正確なコマンド

バックエンド:
```bash
make test           # pytest -q -m "not integration and not perf and not slow"
make lint           # ruff check src tests config scripts
make format-check   # ruff format --check src tests config scripts（line-length 120）
make typecheck      # mypy src。mypy==2.3.1 必須（Makefile がバージョン不一致を fail-fast）
make verify         # ci-parity + lint-layers + typecheck + test-contract + test-migration（PR 前必須）
make test-migration # alembic check + upgrade head + downgrade -1 + upgrade head（リポジトリルートから実行）
make openapi        # docs/openapi.json を生成（API 変更後は必須）
make clean          # キャッシュ・一時 DB ファイルを削除
```

フロントエンド:
```bash
cd frontend
npm run test:ci     # vitest（カバレッジ付き）
npm run lint        # ESLint
npm run typecheck   # tsc --noEmit
npm run type:sync   # OpenAPI エクスポート＋TypeScript 型生成（API 変更後は実行）
cd ..
```

単一テスト: `pytest tests/path/to/test_file.py::test_name -q`。
マーカー: `integration`, `perf`, `slow`, `flaky`, `real_llm`（CI の通常実行では除外）。
`asyncio_mode = auto` なので `@pytest.mark.asyncio` は不要。

カバレッジゲート: `fail_under = 60`（`[tool.coverage.report]`）。CI は `pytest --cov=src --cov-fail-under=60`。

CLI エントリポイント: `autonovel`（`src.cli.main:main`）。例: `autonovel check-env`, `autonovel init-db`, `autonovel export --book-id 1 --format zip`。

## 重要な落とし穴・ルール

1. **mypy バージョンピン**: `make typecheck` はインストール済み mypy が `2.3.1` でないと終了コード 1。ラチェットベースライン（`config/ci_lint_baseline.json`、mypy=450）はバージョン依存のため、不一致だと誤 FAIL/GOOD になる。`pip install 'mypy==2.3.1'` で揃える。
2. **静的解析ラチェット**: `scripts/ci_lint_baseline.json` の ruff=0 / mypy=450 / format=0 を超えると CI 失敗。件数を減らすのは可だが、増やすと fail。`README.md` のベースライン行も `ci_lint_baseline.json` と一致させる必要あり（CI で整合チェック）。
3. **`config/settings.toml`**: gitignore 対象。テスト収集時に不足すれば `conftest.py` が `config/settings.toml.example` から自動生成する。手動作成不要。
4. **Alembic**: `alembic.ini` はリポジトリルート、`script_location = src/backend/alembic`。必ずルートから `alembic` コマンドを実行。本番ではバックエンドコンテナのみマイグレーション実行。ワーカーは `SKIP_ALEMBIC=1` でスキップ（`alembic_version` 主キー重複のクラッシュループ防止）。
5. **OpenAPI スナップショット**: `docs/openapi.json` は CI で `scripts/generate_openapi.py` の出力と diff され、不一致なら失敗。API 変更後は `make openapi` で再生成し、フロントエンドも `npm run type:sync` で型を同期。
6. **バージョン SSOT**: `pyproject.toml` の `project.version` が正。`frontend/package.json`、`src/cli/main.py`、`src/backend/__init__.py` はそれに追随。`tests/regression/test_v5_version_consistency.py` が検証。
7. **恒真 assert / grep ベース assert 禁止**: `tests/regression/test_H1_tautology_guard.py` でブロック。モックなしの素の呼び出しで実挙動を検証する（CONTRIBUTING.md §5.2 参照）。
8. **LLM プロバイダ**: `LLM_PROVIDER=mock` がデフォルト。変更後は API と Huey ワーカー **両方** を再起動。NSFW はデフォルト無効（`ENABLE_NSFW=false`）。
9. **Huey ワーカー**: 生成ジョブはワーカー未起動だと `pending` のまま完了しない。
10. **`.ps1` エンコード**: Windows 起動スクリプトを編集する際は文字コードに注意（`scripts/fix_ps1_encoding.py` 参照。文字化けで起動失敗することがある）。
11. **`.venv` の Python 選択事故**: 空の `.venv` を優先して `fastapi` / `uvicorn` 等が import できなくなることがある。Python 3.12 を明示指定するか、`scripts\start_local.ps1` を使用。

## ディレクトリの役割

| ディレクトリ | 役割 |
|---|---|
| `logs/` | 実行ログ（生成物、gitignore） |
| `artifacts/` / `output/` | ビルド・エクスポート生成物（gitignore） |
| `storage/` | アップロード画像・エクスポートファイルなど永続ストレージ |
| `var/` | 実行時可変データ |
| `benchmarks/` | ベンチマークスクリプト・結果 |
| `.venv/` / `.pytest_cache/` / `.ruff_cache/` / `.mypy_cache/` | 開発キャッシュ（gitignore、`make clean` で削除） |

## ブランチ・コミット規約（CONTRIBUTING.md より）

- ブランチ: `feature/<slug>` / `fix/<slug>`
- コミットメッセージ: Conventional Commits 推奨（`feat:`, `fix:`, `docs:`, `test:`, `chore:`）
- `main` ブランチは常にグリーンを保つ

## PR 前のチェックリスト

- `make verify` を実行（ci-parity、lint-layers、typecheck、test-contract、test-migration）
- `make frontend-test` および `make frontend-lint` を実行
- API 変更があれば `make openapi` で `docs/openapi.json` を更新し、フロントエンド型も同期
- `docs/` を変更したら `mkdocs build --strict` でリンク・厳格チェック
- ユーザー向け変更は `CHANGELOG.md` の Unreleased セクションに追記

参考ドキュメント: `docs/README.md`（ドキュメントインデックス）、`docs/architecture.md`（4層アーキテクチャ）、`docs/STATUS.md`（実装状況 SSOT）、`CONTRIBUTING.md`（コントリビューション詳細）。
