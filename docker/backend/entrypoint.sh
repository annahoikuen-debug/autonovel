#!/bin/bash
# AutoNovel backend コンテナエントリーポイント
#
# 2026-09-27 修正（旧版は `exec "$@"` のみ）:
#   1. Alembic のマイグレーションが一度も実行されておらず、migrations 0001-0030 が
#      既存 DB に適用されない状態だった。`init_db()` は `metadata.create_all` のみで
#      既存テーブルを ALTER できないため、スキーマ変更が適用されなかった。
#   2. `--skip-migrations` が compose の entrypoint 引数 #1 として渡されるが、
#      旧スクリプトはそれを読み取らず（`exec "$@"` で	args としてそのまま uvicorn に
#      渡され）、事実上 no-op になっていた。
#   3. src/backend/alembic/env.py は ALEMBIC_DATABASE_URL を参照するが、未設定時は
#      alembic.ini の `sqlalchemy.url = sqlite:///./autonovel.db` にフォールバックし、
#      本番の PostgreSQL ではなく SQLite にマイグレーションを適用していた。
#      compose 側で ALEMBIC_DATABASE_URL=$DATABASE_URL を設定して解消する。
#
# 使用例:
#   entrypoint.sh uvicorn src.backend.server:app --port 8200   # マイグレーション後に起動
#   entrypoint.sh --skip-migrations uvicorn ...                # マイグレーションをスキップ
set -euo pipefail

SKIP_MIGRATIONS=0

# 先頭のオプションを解析し、残り（実際のコマンド）を COMMAND 配列へ移す。
# 旧実装は引数を丸ごと exec していたため、compose の entrypoint 引数が
# uvicorn に渡され uvicorn が unknown option で落ちていた。
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-migrations)
      SKIP_MIGRATIONS=1
      shift
      ;;
    --run-migrations)
      # ワーカー側でも明示的に適用したい場合の明示指定（既定は 0）
SKIP_MIGRATIONS=0

# 環境変数 SKIP_ALEMBIC=1 でもマイグレーションをスキップする。
# docker-compose.prod.yml の worker サービスは entrypoint の引数ではなく
# 環境変数で渡しているため、両方の経路を受け付ける。
if [[ "${SKIP_ALEMBIC:-0}" == "1" ]]; then
  SKIP_MIGRATIONS=1
fi

      shift
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -eq 0 ]]; then
  echo "[ENTRYPOINT] ERROR: no command given. Usage: entrypoint.sh [--skip-migrations] <command> [args...]" >&2
  exit 64
fi

# Alembic は DATABASE_URL から解決できるようにする。env.py 側の優先順位に依存するが、
# Compose からは両方を渡してどの経路でも同じ DB を指すようにする。
export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL:-${DATABASE_URL:-}}"

if [[ "$SKIP_MIGRATIONS" -eq 1 ]]; then
  echo "[ENTRYPOINT] --skip-migrations specified: skipping 'alembic upgrade head'."
elif [[ -z "$ALEMBIC_DATABASE_URL" ]]; then
  echo "[ENTRYPOINT] WARNING: DATABASE_URL / ALEMBIC_DATABASE_URL is not set." >&2
  echo "[ENTRYPOINT]          'alembic upgrade head' would fall back to the sqlite URL in alembic.ini." >&2
  echo "[ENTRYPOINT]          Refusing to run migrations against an unintended database." >&2
  exit 78   # EX_CONFIG
else
  # 前提: compose 側は depends_on: condition: service_healthy で DB の準備を待ってから
  # backend を起動する。また Huey worker には SKIP_ALEMBIC=1 を渡しており、
  # backend コンテナ 1 台だけが適用する（ワーカーが競合して二重適用しない）。
  echo "[ENTRYPOINT] Running database migrations (alembic upgrade head)..."
  if ! alembic upgrade head; then
    echo "[ENTRYPOINT] ERROR: 'alembic upgrade head' failed. Refusing to start the application." >&2
    exit 1
  fi
  echo "[ENTRYPOINT] Migrations applied successfully."
fi

echo "[ENTRYPOINT] Starting AutoNovel Backend..."
exec "$@"
