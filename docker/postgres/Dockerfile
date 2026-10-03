# AutoNovel v5.0: Apache AGE (Graph DB) の独自ビルドを廃止し、
# 公式 pgvector 軽量イメージへ一本化（ビルド時間短縮 & クラッシュゼロ）
FROM pgvector/pgvector:pg16

# 初期化スクリプト等があれば必要に応じてコピー
#
# 注意: このビルドコンテキストは docker-compose.prod.yml の
# `context: ./docker/postgres` なので、COPY のソースはコンテキスト相対パスになる。
# 従来 `./docker/postgres/init.sql` と書かれており、ビルド時に
# `COPY failed: "/docker/postgres/init.sql": not found` で落ちていた。
#
# なお docker-compose.prod.yml は同じ init.sql を
# /docker-entrypoint-initdb.d へバインドマウントしているため、この COPY は冗長。
# ただし単独 `docker build` でイメージだけ作る用途（compose を使わない場合）を
# 残すため、パスを修正した上で COPY を残す。
COPY ./init.sql /docker-entrypoint-initdb.d/init.sql
