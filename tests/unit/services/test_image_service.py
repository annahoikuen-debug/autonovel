"""ImageService の必須引数 / 振る舞いテスト。

Step 6: api_key 必須化の検証。
Step 32: R15 セーフティ閾値の検証。

NOTE: 現実装は GenAI クライアントを ``client`` プロパティで遅延生成し、
セーフティ設定は ``_build_safety_filter_level`` (GenAI SDK 文字列マッピング) で
返す。旧 ``_build_safety_settings`` / ``settings[0].threshold`` API は廃止済み。
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.models.illustration import SafetyLevel
from src.publishing.illustration.image_service import ImageService


def test_image_service_requires_api_key():
    """Step 6: api_key が空文字 / None なら ValueError。

    NOTE: 実装は api_key 未指定時に settings.get_gemini_api_key() へフォールバック
    するため、先行テストが GOOGLE_GENAI_API_KEY / GEMINI_API_KEY を設定していると
    ValueError にならない。テスト内で環境変数を除去してから検証する。
    """
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GOOGLE_GENAI_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)
        with pytest.raises(ValueError, match="non-empty api_key"):
            ImageService(api_key="")
        with pytest.raises(ValueError, match="non-empty api_key"):
            ImageService(api_key=None)  # type: ignore[arg-type]


def test_image_service_accepts_api_key():
    """正常な api_key なら client プロパティで genai.Client が呼ばれる (mock 化で実 API 抑止)。"""
    with patch("google.genai.Client") as mock_client:
        svc = ImageService(api_key="test-key-xxx")
        assert svc.storage_dir == "static/illustrations"
        # client プロパティに初回アクセスした時点で遅延生成される
        _ = svc.client
        mock_client.assert_called_once_with(api_key="test-key-xxx")


def test_image_service_client_is_lazy():
    """client プロパティに触れない限り genai.Client は生成されない。"""
    with patch("google.genai.Client") as mock_client:
        svc = ImageService(api_key="k")
        assert mock_client.assert_not_called is not None
        assert mock_client.call_count == 0


def test_image_service_r15_safety_block_most():
    """Step 32: R15_CONTENT は最も厳しいフィルタにマップされる。"""
    svc = ImageService(api_key="k")
    level = svc._build_safety_filter_level(SafetyLevel.R15_CONTENT)
    # R15 は BLOCK_MOST 相当 (block_low_and_above)
    assert level == "block_low_and_above"


def test_image_service_block_some_default():
    """デフォルト (BLOCK_SOME) は block_medium_and_above。"""
    svc = ImageService(api_key="k")
    level = svc._build_safety_filter_level(SafetyLevel.BLOCK_SOME)
    assert level == "block_medium_and_above"


def test_image_service_unknown_level_falls_back_to_block_some():
    """未知の level は BLOCK_SOME 相当 (block_medium_and_above) にフォールバック。"""
    svc = ImageService(api_key="k")
    level = svc._build_safety_filter_level("UNKNOWN_LEVEL")
    assert level == "block_medium_and_above"
