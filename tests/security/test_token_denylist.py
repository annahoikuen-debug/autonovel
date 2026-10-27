"""JWT 失効リストとログアウト (改善案 3) の検証。

JWT はステートレスなので、発行してしまったトークンは `exp` まで有効なまま
残る。本ファイルは「ログアウトしたら、そのトークンは署名が正しくても
使えなくなる」ことを固定する。ここが緩いとログアウトが形骸化し、
端末を紛失した際のトークン回収手段が無くなる。
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.backend.config import settings
from src.backend.middleware.auth_middleware import GlobalAuthMiddleware
from src.backend.security import token_denylist
from src.backend.security.jwt import create_access_token, create_refresh_token, decode_token


@pytest.fixture(autouse=True)
def _clean_denylist():
    """テスト間で失効状態が漏れないようにする。"""
    token_denylist.reset()
    yield
    token_denylist.reset()


def _run(coro):
    return asyncio.run(coro)


def _payload(token: str, expected_type: str = "access") -> dict:
    payload = decode_token(token, expected_type=expected_type)
    assert payload is not None, "発行直後のトークンが decode できない"
    return payload


# ---------------------------------------------------------------------------
# 1. トークンに jti が付くこと
# ---------------------------------------------------------------------------


def test_issued_tokens_carry_unique_jti():
    """失効リストのキーになる `jti` が access/refresh 双方に付くこと。"""
    access = create_access_token(user_id=1, role="user")
    refresh = create_refresh_token(user_id=1)

    access_jti = _payload(access)["jti"]
    refresh_jti = _payload(refresh, expected_type="refresh")["jti"]

    assert access_jti
    assert refresh_jti
    # 同一ユーザーでもトークンごとに別 ID。ここが同じだと 1 本を失効させた
    # だけでユーザーの全トークンが吹き飛ぶ。
    assert access_jti != refresh_jti

    another = create_access_token(user_id=1, role="user")
    assert _payload(another)["jti"] != access_jti


def test_old_tokens_without_jti_still_decode():
    """`jti` 導入前に発行されたトークンは失効できないが decode は通る。

    本機能より前に発行されたトークンを突然全滅させないための後方互換。
    """
    import jwt as pyjwt

    from src.backend.security.jwt import get_secret_key

    now = int(time.time())
    legacy = pyjwt.encode(
        {"sub": "1", "role": "user", "type": "access", "exp": now + 3600},
        get_secret_key(),
        algorithm=settings.JWT_ALGORITHM,
    )
    payload = decode_token(legacy, expected_type="access")
    assert payload is not None
    assert payload.get("jti") is None
    # jti が無ければ失効判定は False (_expire まで自然に有効)
    assert _run(token_denylist.is_revoked(payload.get("jti"))) is False


# ---------------------------------------------------------------------------
# 2. 失効リスト本体
# ---------------------------------------------------------------------------


def test_revoke_then_is_revoked():
    token = create_access_token(user_id=1, role="user")
    payload = _payload(token)
    jti = payload["jti"]

    assert _run(token_denylist.is_revoked(jti)) is False

    _run(token_denylist.revoke(jti, payload.get("exp")))

    assert _run(token_denylist.is_revoked(jti)) is True


def test_is_revoked_is_false_for_unknown_and_empty():
    assert _run(token_denylist.is_revoked("does-not-exist")) is False
    assert _run(token_denylist.is_revoked(None)) is False
    assert _run(token_denylist.is_revoked("")) is False


def test_revoke_ignores_empty_jti():
    """`jti` 無しの呼び出しは記録を汚さない。"""
    _run(token_denylist.revoke(None))
    _run(token_denylist.revoke(""))
    assert token_denylist._memory == {}


def test_revoked_entry_expires_with_the_token():
    """失効記録はトークンの残存寿命ぶんしか残らない (無限増加の防止)。"""
    jti = "ttl-probe"
    _run(token_denylist.revoke(jti, exp=time.time() + 2))

    with token_denylist._lock:
        stored_expiry = token_denylist._memory[jti]

    # TTL は 2 秒前後 (丸めで 1〜2 秒)。トークン寿命より長く残らないこと。
    assert 0 < stored_expiry - time.time() <= 3


def test_reset_clears_memory():
    token = create_access_token(user_id=1, role="user")
    payload = _payload(token)
    _run(token_denylist.revoke(payload["jti"], payload.get("exp")))
    assert _run(token_denylist.is_revoked(payload["jti"])) is True

    token_denylist.reset()

    assert _run(token_denylist.is_revoked(payload["jti"])) is False


# ---------------------------------------------------------------------------
# 3. ミドルウェアでの拒否
# ---------------------------------------------------------------------------


def _protected_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(GlobalAuthMiddleware)

    @app.get("/protected")
    def protected():
        return {"ok": True}

    return app


def test_valid_token_passes_middleware(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    client = TestClient(_protected_app())
    token = create_access_token(user_id=1, role="user")

    res = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200


def test_revoked_token_is_rejected_by_middleware(monkeypatch):
    """署名は正しくても、失効させたトークンは 401 になること。"""
    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    client = TestClient(_protected_app())
    token = create_access_token(user_id=1, role="user")
    headers = {"Authorization": f"Bearer {token}"}

    # ログアウト前は通る
    assert client.get("/protected", headers=headers).status_code == 200

    payload = _payload(token)
    _run(token_denylist.revoke(payload["jti"], payload.get("exp")))

    res = client.get("/protected", headers=headers)
    assert res.status_code == 401
    # 有効期限切れと区別できないメッセージにする (トークンの状態を漏らさない)
    assert res.json() == {"detail": "無効または期限切れのトークンです"}


def test_revoked_token_does_not_affect_other_tokens(monkeypatch):
    """あるトークンを失効させても、別のトークンはそのまま使えること。"""
    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    client = TestClient(_protected_app())

    revoked = create_access_token(user_id=1, role="user")
    other = create_access_token(user_id=1, role="user")

    payload = _payload(revoked)
    _run(token_denylist.revoke(payload["jti"], payload.get("exp")))

    assert (
        client.get("/protected", headers={"Authorization": f"Bearer {revoked}"}).status_code
        == 401
    )
    assert (
        client.get("/protected", headers={"Authorization": f"Bearer {other}"}).status_code
        == 200
    )


# ---------------------------------------------------------------------------
# 4. ログアウト API
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    from src.backend.server import app

    with TestClient(app) as client:
        yield client


def test_logout_revokes_the_presented_access_token(api_client):
    token = create_access_token(user_id=1, role="user")
    payload = _payload(token)

    res = api_client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200, res.text
    assert _run(token_denylist.is_revoked(payload["jti"])) is True


def test_logout_requires_a_token(api_client):
    """トークン無しのログアウトは何も失効させられない。"""
    res = api_client.post("/api/auth/logout")

    assert res.status_code == 401


def test_logout_with_garbage_token_is_rejected(api_client):
    res = api_client.post(
        "/api/auth/logout", headers={"Authorization": "Bearer not.a.token"}
    )

    assert res.status_code == 401


def test_logout_also_revokes_refresh_token_when_provided(api_client):
    """クライアントがリフレッシュトークンを持っていたら併せて失効する。

    これを怠るとログアウト後もリフレッシュ経由でアクセストークンを取り直せてしまう。
    """
    access = create_access_token(user_id=1, role="user")
    refresh = create_refresh_token(user_id=1)
    refresh_jti = _payload(refresh, expected_type="refresh")["jti"]

    res = api_client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
        json={"refresh_token": refresh},
    )

    assert res.status_code == 200, res.text
    assert _run(token_denylist.is_revoked(refresh_jti)) is True


def test_refresh_rejects_revoked_refresh_token(api_client):
    """失効済みリフレッシュトークンは新しいアクセストークンを発行しない。"""
    refresh = create_refresh_token(user_id=1)
    payload = _payload(refresh, expected_type="refresh")
    _run(token_denylist.revoke(payload["jti"], payload.get("exp")))

    res = api_client.post(
        "/api/auth/refresh", headers={"Authorization": f"Bearer {refresh}"}
    )

    assert res.status_code == 401
