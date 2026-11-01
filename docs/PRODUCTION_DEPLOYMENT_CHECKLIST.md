# 本番デプロイ前チェックリスト

AutoNovel を本番環境にデプロイする前に、以下の項目をすべて確認してください。

---

## 1. 必須環境変数

以下の環境変数が `.env` またはデプロイ先のシークレットに設定されていること。

| 変数 | 説明 | 例 |
|------|------|----|
| `APP_ENV` | `production` に設定。未設定だと `development` フォールバックとなり認証バイパスが発生する | `production` |
| `JWT_SECRET_KEY` | JWT 署名鍵。`openssl rand -hex 32` で生成。ワーカー間で同一であること | `a1b2c3...` |
| `ALLOWED_API_KEYS` | 許容する API キー（カンマ区切り）。空不可 | `key1,key2` |
| `CORS_ORIGINS` | 許可オリジン（カンマ区切り）。`*` は production で拒否される | `https://novel.example.com` |
| `POSTGRES_PASSWORD` | PostgreSQL パスワード | `secure_password` |
| `REDIS_PASSWORD` | Redis `--requirepass` パスワード | `secure_password` |
| `DATABASE_URL` | PostgreSQL 接続 URL | `postgresql+psycopg2://autonovel:...@postgres:5432/autonovel` |
| `ALEMBIC_DATABASE_URL` | マイグレーション用 DB URL。`DATABASE_URL` と同じ値 | 同上 |
| `REDIS_URL` | Redis 接続 URL | `redis://:password@redis:6379/0` |

### 任意環境変数（既定あり）

| 変数 | 説明 | 既定値 |
|------|------|--------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | アクセストークン有効期限（分） | `60` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | リフレッシュトークン有効期限（日） | `14` |
| `UVICORN_WORKERS` | uvicorn ワーカー数。1 より大きい場合は `JWT_SECRET_KEY` が固定であること | `1` |
| `FRONTEND_URL` | フロントエンド URL | `http://localhost:8080` |
| `HOST` / `PORT` | 待ち受けアドレスとポート | `0.0.0.0` / `8200` |
| `LLM_PROVIDER` | 推論エンジン | `openai` |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | LLM API キー | 未設定（モック動作） |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Stripe 決済（未設定なら課金無効化） | 未設定 |
| `ENABLE_NSFW` | 官能コンテンツ生成の明示オプトイン。既定 `false`（デフォルト拒否） | `false` |

---

## 2. フロントエンド環境変数（Vercel / docker-compose）

| 変数 | 説明 | 設定先 |
|------|------|--------|
| `VITE_API_BASE_URL` | API ベース URL | Vercel env / docker-compose |
| `VITE_GA4_MEASUREMENT_ID` | GA4 測定 ID | Vercel env |
| `VITE_SENTRY_DSN` | Sentry DSN | Vercel env |
| `VITE_SITE_URL` | 本番オリジン（canonical / OGP 用）。未設定時は相対パスになる | Vercel env / docker-compose |

> `VITE_SITE_URL` が未設定だと `canonical` / `ogImage` が `/` や `/ogp.png` などの相対パスになり、検索エンジンに正しく伝わらない可能性がある。本番ドメイン（例: `https://novel.example.com`）を設定すること。

---

## 3. ストレージ永続化

以下の Docker ボリュームがマウントされていること。

| ボリューム | 用途 |
|-----------|------|
| `autonovel_pgdata` | PostgreSQL データ |
| `autonovel_redis` | Redis データ（Huey キュー） |
| `autonovel_storage` | 生成済み章・アップロード画像・エクスポートファイル |
| `autonovel_logs` | アプリケーションログ |

> `docker compose down -v` でボリュームも削除されるとデータが消失する点に注意。

---

## 4. マイグレーション

- backend コンテナ 1 台だけが `alembic upgrade head` を実行する。
- worker は `SKIP_ALEMBIC=1` でマイグレーションをスキップし、二重実行（`alembic_version` 主キー重複）を防ぐ。
- マイグレーションは `docker compose up` 時に自動実行される（backend の entrypoint）。

---

## 5. 品質ゲート（CI で自動チェック）

以下の項目が CI でグリーンであること。

| ゲート | 内容 | コマンド |
|--------|------|----------|
| ruff | `scripts/ci_lint_ratchet.py --tool ruff` | ベースライン超過で fail |
| mypy | `scripts/ci_lint_ratchet.py --tool mypy` | ベースライン超過で fail |
| format | `scripts/ci_lint_ratchet.py --tool format` | ベースライン超過で fail |
| テスト | `pytest -q --cov=src --cov-fail-under=60` | カバレッジ 60% 未満で fail |
| 長編耐性 | `python -m tests.benchmarks.long_form --eps 200 --check` | 閾値違反で fail |
| リリース整合性 | `pytest tests/regression/test_v5_version_consistency.py` | バージョン不整合で fail |

---

## 6. NSFW オプトイン（セキュリティ）

- `ENABLE_NSFW` は既定 `false`（デフォルト拒否）。
- `true` にする場合は、運用チームに事前通知し、監査ログ出力を確認すること。
- 官能生成時のログは `nsfw_generation` イベントとして構造化ログに出力される。

---

## 7. デプロイ手順

```bash
# 1. 環境変数ファイルを用意
cp .env.example .env

# 2. 必須値を設定（JWT_SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD, CORS_ORIGINS など）

# 3. 本番起動
docker compose -f docker-compose.prod.yml up -d --build

# 4. ヘルスチェック
curl http://localhost:8200/health

# 5. フロントエンドアクセス確認
curl http://localhost:8080
```

---

## 8. ロールバック手順

```bash
# コンテナ停止
docker compose -f docker-compose.prod.yml down

# 前バージョンイメージにタグを戻して再起動（必要に応じて）
docker compose -f docker-compose.prod.yml up -d
```

---

> このチェックリストは `docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md` として管理され、デプロイ前に必ず確認すること。
