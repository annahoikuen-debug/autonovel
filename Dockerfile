# ==========================================
# Stage 1: Build dependencies
# ==========================================
ARG PYTHON_VERSION=3.12-slim
FROM python:${PYTHON_VERSION} AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ホイールをビルドしてキャッシュ効率化 (Step 11)
# 依存は /opt/deps に隔離し、runner ステージから最小限コピーする
COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/opt/deps -r requirements.txt

# ==========================================
# Stage 2: Minimal Runtime
# ==========================================
FROM python:${PYTHON_VERSION} AS runner
WORKDIR /app

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/appuser/.local/bin:$PATH

# ランタイムに必要な共有ライブラリのみインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 非特権ユーザーの作成
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    mkdir -p /app/storage /app/logs && \
    chown -R appuser:appuser /app

# builderステージからインストール済みパッケージを最小限コピー (Step 11)
COPY --from=builder --chown=appuser:appuser /opt/deps /home/appuser/.local

# アプリケーションソースのコピー
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser database/ ./database/
COPY --chown=appuser:appuser docker/backend/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY --chown=appuser:appuser formatters/ ./formatters/
COPY --chown=appuser:appuser plugins/ ./plugins/
COPY --chown=appuser:appuser prompts/ ./prompts/
COPY --chown=appuser:appuser schemas/ ./schemas/
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser pyproject.toml ./

RUN chmod +x /usr/local/bin/entrypoint.sh

USER appuser
EXPOSE 8200

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
# ワーカー数は環境変数 UVICORN_WORKERS で制御する。旧 CMD は `--workers 1` を
# ハードコードしており、docker-compose.prod.yml が広告している UVICORN_WORKERS が
# 一切効かなかった（環境変数としては渡されるが参照されない死んだ設定だった）。
# "${UVICORN_WORKERS:-1}" はこの行では展開されず、実行時に sh が展開する。
# 既定を 1 未満にしないよう、UVICORN_WORKERS 未設定時は必ず 1 で起動する。
# ただし APP_ENV=production では JWT_SECRET_KEY が全ワーカーで同一である必要がある
# （未設定だとワーカーごとに secrets.token_hex(32) が生成され、署名済みトークンが
# ワーカー間で不一致になる）。docker-compose.prod.yml 側で fail-fast 設定済み。
CMD ["sh", "-c", "exec uvicorn src.backend.server:app --host 0.0.0.0 --port 8200 --workers ${UVICORN_WORKERS:-1}"]
