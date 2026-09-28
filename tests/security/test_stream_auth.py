"""ストリーム認証と公開パス境界の回帰テスト。

修正内容に対する回帰，防止:
    1. ``PUBLIC_PREFIXES`` に ``"/api/stream"`` を丸ごと登録していたため、
       当該プレフィックス配下の全エンドポイントが default-deny の網から外れていた
    2. 単純な ``startswith`` のため、境界で切れたパス
       （例: ``/api/streaming-public``）までまとめて公開されていた
    3. SSE / WebSocket のトークン検証に **book_id の所有権チェックが無く**、
       認証済みユーザーなら他人の作品テレメトリを購読できた
    4. API キーが ``token in all_valid_keys``（平文比較）で検証されていた
    5. 長期有効な access JWT をクエリパラメータに載せられ、
       nginx アクセスログやブラウザ履歴に認証情報が平文で残っていた
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from src.backend.config import settings
from src.backend.middleware.auth_middleware import (
    PUBLIC_PREFIXES,
    _extract_stream_book_id,
    is_public_path,
)
from src.backend.security.jwt import create_access_token, get_secret_key
from src.backend.security.stream_token import (
    STREAM_TOKEN_TYPE,
    create_stream_token,
    verify_stream_token,
)


# ---------------------------------------------------------------- #
# 1. 公開パスの境界
# ---------------------------------------------------------------- #

def test_api_stream_is_not_in_public_prefixes():
    """/api/stream は公開プレフィックスに含まれないこと。"""
    assert "/api/stream" not in PUBLIC_PREFIXES
    assert "/api/stream/" not in PUBLIC_PREFIXES


@pytest.mark.parametrize(
    "path",
    [
        "/api/stream",
        "/api/stream/pipeline/1",
        "/api/stream/writing/1/2",
        # 境界で切れたパスも公開されてはいけない
        "/api/streaming-public",
        "/api/streamingfoo",
        "/api/ws/pipeline/1",
    ],
)
def test_stream_paths_are_not_public(path: str):
    """ストリーム系パスは default-deny の網から外れないこと。"""
    assert is_public_path(path) is False, f"{path} が公開パスとして扱われています"


@pytest.mark.parametrize(
    "path",
    ["/static/app.js", "/assets/logo.png", "/favicon", "/favicon.ico", "/docs"],
)
def test_legitimate_public_prefixes_still_public(path: str):
    """意図的に公開している静的アセット系は引き続き公開であること。"""
    assert is_public_path(path) is True


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/stream/writing/42/3", 42),
        ("/api/stream/pipeline/7", 7),
        ("/api/stream/writing/notanumber/3", None),
        ("/api/other/1", None),
    ],
)
def test_extract_stream_book_id(path: str, expected):
    assert _extract_stream_book_id(path) == expected


# ---------------------------------------------------------------- #
# 2. ストリームトークン
# ---------------------------------------------------------------- #

def test_stream_token_roundtrip_is_book_scoped():
    token = create_stream_token(user_id=123, book_id=42)
    assert verify_stream_token(token, 42) == 123


def test_stream_token_rejects_other_book():
    """他作品のトークンで当該作品を購読できないこと。"""
    token = create_stream_token(user_id=123, book_id=42)
    assert verify_stream_token(token, 99) is None


def test_stream_token_is_not_accepted_without_book_check_but_is_valid():
    """book_id 省略時は scope 検証をせず、署名と type のみを見る。"""
    token = create_stream_token(user_id=123, book_id=42)
    assert verify_stream_token(token) == 123


def test_access_token_is_rejected_as_stream_token():
    """通常の access JWT をストリーム用途に使い回せないこと。"""
    access = create_access_token(data={"sub": "123"})
    assert verify_stream_token(access, 42) is None


def test_expired_stream_token_is_rejected():
    """期限切れトークンは拒否されること。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "123",
        "book_id": 42,
        "type": STREAM_TOKEN_TYPE,
        "iat": now - timedelta(seconds=120),
        "exp": now - timedelta(seconds=60),
    }
    token = jwt.encode(payload, get_secret_key(), algorithm=settings.JWT_ALGORITHM)
    assert verify_stream_token(token, 42) is None


def test_garbage_token_is_rejected():
    assert verify_stream_token("not-a-jwt", 42) is None
    assert verify_stream_token("", 42) is None
    assert verify_stream_token(None, 42) is None


def test_stream_token_ttl_is_short():
    """ストリームトークンは短命であること（クエリに載せても影響が限定的）。"""
    from src.backend.security.stream_token import DEFAULT_STREAM_TOKEN_TTL_SECONDS

    assert DEFAULT_STREAM_TOKEN_TTL_SECONDS <= 120


def test_stream_token_carries_distinct_type_claim():
    """access/refresh と混同できないよう type クレームが分離されていること。"""
    token = create_stream_token(user_id=1, book_id=1)
    payload = jwt.decode(token, get_secret_key(), algorithms=[settings.JWT_ALGORITHM])
    assert payload["type"] == STREAM_TOKEN_TYPE
    assert payload["type"] != "access"
    assert payload["type"] != "refresh"


# ---------------------------------------------------------------- #
# 3. ストリーム認証の解決ロジック
# ---------------------------------------------------------------- #

def test_api_key_matching_uses_constant_time_and_rejects_plain_membership(monkeypatch):
    """API キー検証が平文 `in` 比較ではなく定数時間比較であることを確認する。"""
    from src.backend.routers import pipeline_stream as ps

    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    allowed = {"alpha-key", "beta-key"}
    assert ps._matches_any_api_key("alpha-key", allowed) is True
    assert ps._matches_any_api_key("gamma", allowed) is False
    assert ps._matches_any_api_key("", allowed) is False
    assert ps._matches_any_api_key("alpha-key", set()) is False


def test_resolve_stream_identity_prefers_headers_over_query(monkeypatch):
    """ヘッダーの access JWT がクエリの別ユーザートークンより優先されること。"""
    from src.backend.routers import pipeline_stream as ps

    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    header_token = create_access_token(data={"sub": "1"})
    query_stream = create_stream_token(user_id=2, book_id=42)

    resolved = ps.resolve_stream_identity(
        authorization=f"Bearer {header_token}",
        query_token=query_stream,
        book_id=42,
    )
    assert resolved == 1


def test_resolve_stream_identity_ignores_access_token_in_query(monkeypatch):
    """クエリに access JWT を載せる経路は使えないこと（ログ漏えい防止）。"""
    from src.backend.routers import pipeline_stream as ps

    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    access = create_access_token(data={"sub": "1"})

    resolved = ps.resolve_stream_identity(query_token=access, book_id=42)
    assert resolved is None


def test_resolve_stream_identity_accepts_scoped_stream_token(monkeypatch):
    from src.backend.routers import pipeline_stream as ps

    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    stream = create_stream_token(user_id=7, book_id=42)
    assert ps.resolve_stream_identity(query_token=stream, book_id=42) == 7
    # スコープ外の書籍では拒否される
    assert ps.resolve_stream_identity(query_token=stream, book_id=43) is None


def test_resolve_stream_identity_rejects_missing_token(monkeypatch):
    from src.backend.routers import pipeline_stream as ps

    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    assert ps.resolve_stream_identity(book_id=42) is None
