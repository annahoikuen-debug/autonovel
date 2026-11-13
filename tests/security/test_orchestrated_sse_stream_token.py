"""Step 7 (H6): クラッシュリカバリ SSE のストリームトークン認証。

H6: EventSource は Authorization ヘッダーを送信できず、バックエンドが
get_current_user を要求していたため常に 401 になっていた。短命ストリーム
トークン（?token=）で認証・作品スコープ所有権を検証するよう修正。
"""
from __future__ import annotations

from src.backend.security.stream_token import (
    create_stream_token,
    verify_stream_token,
)


def test_verify_stream_token_valid():
    """有効なストリームトークンは user_id を返す（H6）。"""
    user_id = verify_stream_token(
        create_stream_token(user_id=42, book_id=7), book_id=7
    )
    assert user_id == 42


def test_verify_stream_token_wrong_book_id():
    """book_id が一致しないストリームトークンは None を返す（H6 IDOR 防止）。"""
    user_id = verify_stream_token(
        create_stream_token(user_id=42, book_id=7), book_id=99
    )
    assert user_id is None


def test_verify_stream_token_invalid():
    """無効なトークンは None を返す（H6）。"""
    assert verify_stream_token("invalid.token.value", book_id=7) is None
    assert verify_stream_token("", book_id=7) is None
    assert verify_stream_token(None, book_id=7) is None
