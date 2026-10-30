"""JWT トークン発行関数の公開シグネチャ契約（リグレッション防止）。

`create_access_token` / `create_refresh_token` の公開引数は
`user_id` / `role` / `extra_claims` であり、これらは後方互換を破る
引数改名の対象にしない。旧 `data=` API への後戻りも本テストで検出する。

過去に `create_access_token(data={...})` という旧 API を前提とした
テストが `TypeError: unexpected keyword argument 'data'` で失敗した
（PLAN_J1 W2）。本契約テストにより、今後のシグネチャ変更は即座に赤くなる。
"""
from __future__ import annotations

import inspect

from src.backend.security.jwt import create_access_token, create_refresh_token


def test_create_access_token_signature_contract() -> None:
    """create_access_token の公開シグネチャを固定する。"""
    params = inspect.signature(create_access_token).parameters

    # 第一引数 user_id（位置引数）
    assert "user_id" in params, "create_access_token は user_id 引数を公開していること"
    assert params["user_id"].kind in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ), "user_id は位置引数であること"

    # キーワード専用引数
    for name in ("role", "extra_claims"):
        assert name in params, f"create_access_token は {name} 引数を公開していること"
        assert params[name].kind == inspect.Parameter.KEYWORD_ONLY, (
            f"{name} はキーワード専用引数であること"
        )

    # 既定値の契約
    assert params["role"].default == "user", "role の既定値は 'user' であること"

    # 旧 data= API が復活していないこと
    assert "data" not in params, (
        "旧 create_access_token(data={...}) API へ後戻りしていないこと"
    )


def test_create_refresh_token_signature_contract() -> None:
    """create_refresh_token の公開シグネチャを固定する。"""
    params = inspect.signature(create_refresh_token).parameters

    assert "user_id" in params, "create_refresh_token は user_id 引数を公開していること"
    assert params["user_id"].kind in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ), "user_id は位置引数であること"

    assert "extra_claims" in params, (
        "create_refresh_token は extra_claims 引数を公開していること"
    )
    assert params["extra_claims"].kind == inspect.Parameter.KEYWORD_ONLY, (
        "extra_claims はキーワード専用引数であること"
    )

    assert "data" not in params, (
        "旧 create_refresh_token(data={...}) API へ後戻りしていないこと"
    )


def test_tokens_issued_with_public_signature_are_decodable() -> None:
    """公開シグネチャで発行したトークンが decode_token で解決できること。

    シグネチャ契約が「呼び出し可能」だけでなく「実際に機能する」ことを
    保証する（decoding 面からのリグレッション防止）。
    """
    from src.backend.security.jwt import decode_token

    access = create_access_token(user_id=101, role="user")
    payload = decode_token(access, expected_type="access")
    assert payload is not None, "公開シグネチャで発行したアクセストークンが decode 可能であること"
    assert payload["sub"] == "101", "user_id が sub クレームに設定されること"
    assert payload["role"] == "user", "role が role クレームに設定されること"

    refresh = create_refresh_token(user_id=101)
    refresh_payload = decode_token(refresh, expected_type="refresh")
    assert refresh_payload is not None, "公開シグネチャで発行したリフレッシュトークンが decode 可能であること"
    assert refresh_payload["sub"] == "101", "user_id が sub クレームに設定されること"
