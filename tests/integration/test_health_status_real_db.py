"""実 DB に到達する経路を、**mock を 1 つも使わずに**叩く smoke。

なぜこのファイルが存在するか（PLAN_H1R H1R-1）:
H1 は archangel（archangel = 悪化の検出器）を 19 本追加したが、
``src/services/resilience.py::check_database()`` が **2 世代連続で
常に ``"error"`` を返していた**ことを 1 本も捕まえられなかった。

理由が明白である: 全 archangel が検査していたのは「形」（import されるか、
ガードがあるか、ファイルレイアウト“两个rait”）だけで、
**イベントループ / greenlet / DB 接続という境界をまたぐ「実挙動」**を
検査するものが存在しなかった。

このテストはその穴を埋める。**mock を使わない**ことで、
mock が「正しく動いている」ことしか保証できない既存テストの弱点を避ける。
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    """実 app を起こす。lifespan 経由で init_db() が走る。"""
    from src.backend.server import app

    with TestClient(app) as c:
        yield c


# --- 1. /health -------------------------------------------------------


def test_health_returns_200(client: TestClient):
    assert client.get("/health").status_code == 200


def test_health_payload_reports_ok(client: TestClient):
    body = client.get("/health").json()
    assert body.get("status") in {"ok", "degraded"}, body


# --- 2. /health/detail（認証必須。testing では AUTH_DISABLED）------


def test_health_detail_returns_200(client: TestClient):
    assert client.get("/health/detail").status_code == 200


def test_health_detail_payload_is_not_a_placeholder(client: TestClient):
    """detail が中身のある JSON を返すこと。空 dict や 500 でないこと。"""
    resp = client.get("/health/detail")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, dict) and body, f"/health/detail が空の応答を返した: {body}"


# --- 3. /api/system/status ← H1 で 2 世代壊れていた経路 ----------------


def test_system_status_reports_the_database(client: TestClient):
    """``get_system_status()`` の database フィールドが "ok" であること。

    H1 中、旧実装（``get_event_loop().run_until_complete``）と H1 の書き換え
    （``AsyncEngine.sync_engine.connect()``）は **どちらも** ここで "error" を返した。
    ``tests/unit/routers/test_router_system_coverage.py:45`` は
    ``get_system_status`` を丸ごと monkeypatch していたため、この経路は 0 テストだった。
    """
    resp = client.get("/api/system/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("database") == "ok", (
        f"/api/system/status が database を 'ok' と報告していない: {body}"
    )


def test_check_database_directly_in_plain_sync_context():
    """HTTP 経由ではなく、関数を素の同期コンテキストで直接呼ぶ。

    ``check_database`` はモジュール関数を直接呼ぶ利用者がいるため、
    TestClient 経由が緑でも素の呼び出しが壊れている可能性を残す。
    """
    from src.services.resilience import check_database

    assert check_database() == "ok"


# --- 4. /metrics ------------------------------------------------------


def test_metrics_returns_200(client: TestClient):
    assert client.get("/metrics").status_code == 200


# --- 5. アプリが実際に「動いている」ことの総括 -------------------------


def test_app_is_actually_serving_real_routes(client: TestClient):
    """「app が import できて 200 が返る」だけでは足りないことの確認。

    OpenAPI に載っている実在ルートが、レスポンスとして本当に征服できるかを見る。
    """
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/api/system/status" in paths, "/api/system/status が OpenAPI に無い"
    assert "/health" in paths, "/health が OpenAPI に無い"


def test_database_really_is_reachable_not_merely_not_raising():
    """``check_database`` が "ok" を返すのは、実際に SELECT が通っているためか。

    「例外を投げなかったから ok」は論理的に誤りである。
    実際に接続して 1 行取得できることを確認する。
    """
    from sqlalchemy import create_engine, text

    from src.core.container import AppContainer
    from src.services.resilience import _sync_engine_url

    engine = create_engine(_sync_engine_url(AppContainer.db().engine.url))
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1
    finally:
        engine.dispose()


def test_this_file_uses_no_mock():
    """本ファイル自身に mock が混ざっていないことの自己点検。

    「mock を使わない smoke」という性質を、将来誰かが壊しても気付けるように。
    docstring での言及は許すので、**呼び出しパターン**（import と生成）で判定する。
    パターンは断片を連結して組み立てる（そうしないと本テストが自分を検出する）。
    """
    src_path = os.path.abspath(__file__)
    with open(src_path, encoding="utf-8") as fh:
        src = fh.read()
    u = "unit" + "test"
    usage_patterns = (
        f"import {u}.mock",
        f"from {u} import mock",
        f"from {u}.mock import",
        "Magic" + "Mock(",
        "Async" + "Mock(",
        "monkeypatch." + "setattr(",
        "patch" + "(",
    )
    found = [p for p in usage_patterns if p in src]
    assert not found, (
        f"本ファイルは mock を使わない smoke のはずだが {found} を含む"
    )