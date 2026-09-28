"""
tests/unit/publishers/test_kakuyomu.py - カクヨムPublisherテスト

注意: カクヨムには公式の投稿APIが存在しないため、Step 16/17 で架空の
REST API（api.kakuyomu.jp）実装は完全に撤廃された。現行仕様は
「整形済み本文 + 『エピソード新規作成画面』URL」を返す手動投稿支援のみ。
そのため本ファイルは HTTP クライアント（_client）を前提とした旧仕様の
テストではなく、現行の URL 生成・整形・検証の振る舞いを検証する。
"""

from __future__ import annotations

import pytest

from src.services.publishers.kakuyomu import (
    KAKUYOMU_EPISODE_NEW_URL_TEMPLATE,
    KakuyomuPublisher,
    KakuyomuCredentials,
)
from src.services.publishers.base import ValidationError


class TestKakuyomuPublisher:
    """KakuyomuPublisherテスト"""

    @pytest.fixture
    def publisher(self):
        return KakuyomuPublisher(timeout=10.0)

    @pytest.fixture
    def credentials(self):
        return KakuyomuCredentials(api_token="test_token_123", user_id="user_456")

    def test_publisher_initialization(self, publisher):
        """初期化テスト"""
        assert publisher.platform == "kakuyomu"
        assert publisher.description == "カクヨム（ワンクリック整形コピー + 投稿画面URL生成）"
        # 手動投稿支援モードのためレート制限は実質無制限
        assert publisher.rate_limit_per_minute == 60
        assert publisher.rate_limit_per_hour == 3600
        assert publisher.timeout == 10.0

    def test_no_http_client_attribute(self, publisher):
        """HTTPクライアントは存在しない（外部API撤廃済み）。"""
        assert not hasattr(publisher, "_client")

    @pytest.mark.asyncio
    async def test_authenticate_success(self, publisher, credentials):
        """認証はHTTPなしで成功扱い（手動投稿支援モード）。"""
        assert await publisher.authenticate(credentials) is True

    @pytest.mark.asyncio
    async def test_authenticate_missing_token(self, publisher):
        """トークンなしでも認証エラーにはならない。"""
        creds = KakuyomuCredentials()

        assert await publisher.authenticate(creds) is True

    @pytest.mark.asyncio
    async def test_publish_success(self, publisher, credentials):
        """投稿はHTTPなしでハンドオフを返す。"""
        novel = {
            "work_id": "work_123",
            "title": "テスト小説",
            "synopsis": "あらすじ",
            "genre": "fantasy",
            "tags": ["ファンタジー"],
        }
        chapter = {"ep_num": 1, "title": "第1話", "content": "本文テスト"}

        result = await publisher.publish(novel, chapter, credentials)

        assert result.success is True
        assert result.platform == "kakuyomu"
        assert result.post_id == "work_123"
        assert result.url == KAKUYOMU_EPISODE_NEW_URL_TEMPLATE.format(work_id="work_123")
        assert result.metadata["work_id"] == "work_123"
        assert result.metadata["episode_creation_url"] == result.url
        assert result.metadata["title"] == "テスト小説"
        assert result.metadata["body"] == "本文テスト"
        assert result.metadata["total_characters"] == len("本文テスト")

    @pytest.mark.asyncio
    async def test_publish_validation_error(self, publisher, credentials):
        """work_id 欠落時は ValidationError（URL生成できないため）。"""
        with pytest.raises(ValidationError) as exc_info:
            await publisher.publish({"title": "Test"}, {"ep_num": 1}, credentials)

        assert "work_id" in str(exc_info.value)
        assert exc_info.value.platform == "kakuyomu"

    @pytest.mark.asyncio
    async def test_publish_blank_work_id_rejected(self, publisher, credentials):
        """空白だけの work_id も欠落扱い。"""
        with pytest.raises(ValidationError):
            await publisher.publish({"work_id": "   "}, {"ep_num": 1}, credentials)

    @pytest.mark.asyncio
    async def test_update_chapter(self, publisher, credentials):
        """話追加はHTTPなしでハンドオフを返す。"""
        chapter = {"ep_num": 2, "title": "第2話", "content": "第2話本文"}

        result = await publisher.update_chapter("work_123", chapter, credentials)

        assert result.success is True
        assert result.post_id == "work_123"
        assert result.metadata["episode_number"] == 2
        assert result.metadata["body"] == "第2話本文"

    @pytest.mark.asyncio
    async def test_update_chapter_not_found(self, publisher, credentials):
        """post_id（作品ID）が空なら ValidationError。"""
        with pytest.raises(ValidationError) as exc_info:
            await publisher.update_chapter("   ", {"ep_num": 2}, credentials)

        assert "作品ID" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_post_status(self, publisher, credentials):
        """ステータス取得は作品ページURLのみ返す。"""
        status = await publisher.get_post_status("work_123", credentials)

        assert status["work_id"] == "work_123"
        assert status["status"] == "manual_publish"
        assert status["url"] == "https://kakuyomu.jp/works/work_123"
        assert status["episode_creation_url"].endswith("/episodes/new")

    def test_format_for_kakuyomu(self, publisher):
        """カクヨム用フォーマットテスト"""
        content = "第1行\n\n第2行\n\n\n第3行"
        formatted = publisher._format_for_kakuyomu(content)

        # 改行正規化 + 前後の空白除去
        assert formatted == "第1行\n\n第2行\n\n\n第3行"
        assert "\r" not in publisher._format_for_kakuyomu("a\r\nb\rc")
