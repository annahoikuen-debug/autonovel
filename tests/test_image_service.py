"""ImageService の必須引数 / 振る舞いテスト。

Step 6: api_key 必須化の検証。
Step 32: R15 セーフティ閾値の検証。
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.models.illustration import SafetyLevel
from src.services.image_service import ImageService


def test_image_service_requires_api_key(monkeypatch):
    """Step 6: api_key が空文字 / None なら ValueError。

    環境変数や .env 由来のダミーキーが解決されないよう、
    env から Gemini 系キーを除去してから検証する。
    """
    for var in ("GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("src.backend.config.settings.GEMINI_API_KEY", None)
    with pytest.raises(ValueError, match="non-empty api_key"):
        ImageService(api_key="")
    with pytest.raises(ValueError, match="non-empty api_key"):
        ImageService(api_key=None)  # type: ignore[arg-type]


def test_image_service_accepts_api_key():
    """正常な api_key なら genai.Client が呼ばれる (mock 化で実 API 抑止)。

    image_service は genai を遅延 import するため、SDK のモジュールを
    直接 patch する。
    """
    with patch("google.genai.Client") as mock_client:
        svc = ImageService(api_key="AIzaSyTest0123456789abcdef")
        assert svc.storage_dir == "static/illustrations"
        # client は遅延生成のため、プロパティアクセスで Client が構築される
        _ = svc.client
        mock_client.assert_called_once_with(api_key="AIzaSyTest0123456789abcdef")


def test_image_service_r15_safety_block_most():
    """Step 32: R15_CONTENT は block_low_and_above にマップされる。"""
    with patch("google.genai.Client"):
        svc = ImageService(api_key="k")
        level = svc._build_safety_filter_level(SafetyLevel.R15_CONTENT)
        assert level == "block_low_and_above"


def test_image_service_block_some_default():
    """デフォルト (BLOCK_SOME) は block_medium_and_above。"""
    with patch("google.genai.Client"):
        svc = ImageService(api_key="k")
        level = svc._build_safety_filter_level(SafetyLevel.BLOCK_SOME)
        assert level == "block_medium_and_above"


def test_image_service_unknown_level_falls_back_to_block_some():
    """未知の level は block_medium_and_above にフォールバック。"""
    with patch("google.genai.Client"):
        svc = ImageService(api_key="k")
        level = svc._build_safety_filter_level("UNKNOWN_LEVEL")
        assert level == "block_medium_and_above"
