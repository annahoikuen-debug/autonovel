"""SPINE_QUALITY 設定の契約。

壊れ方: 設定キーの名前衝突・既定値の変更・未知値の扱い変更 → 赤。
"""

from __future__ import annotations

import os

import pytest

from src.llm.adapters.prompts import get_spine_quality, SPINE_QUALITY_ENV, SPINE_QUALITY_LEVELS


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """テスト間で SPINE_QUALITY 環境変数が漏れないよう、各テスト前後にクリアする。"""
    monkeypatch.delenv(SPINE_QUALITY_ENV, raising=False)
    yield
    monkeypatch.delenv(SPINE_QUALITY_ENV, raising=False)


def test_env_const_is_spine_quality():
    """環境変数名が SPINE_QUALITY であること（src/llm/adapters/prompts.py の SSOT）。"""
    assert SPINE_QUALITY_ENV == "SPINE_QUALITY"


def test_levels_are_off_soft_hard():
    """適用レベルが off/soft/hard のみであること。"""
    assert SPINE_QUALITY_LEVELS == ("off", "soft", "hard")


def test_default_is_off():
    """未設定のとき既定値は "off" であること。"""
    assert get_spine_quality() == "off"


def test_explicit_off_is_off(monkeypatch):
    """SPINE_QUALITY=off のとき off を返すこと。"""
    monkeypatch.setenv(SPINE_QUALITY_ENV, "off")
    assert get_spine_quality() == "off"


def test_explicit_soft_is_soft(monkeypatch):
    """SPINE_QUALITY=soft のとき soft を返すこと。"""
    monkeypatch.setenv(SPINE_QUALITY_ENV, "soft")
    assert get_spine_quality() == "soft"


def test_explicit_hard_is_hard(monkeypatch):
    """SPINE_QUALITY=hard のとき hard を返すこと。"""
    monkeypatch.setenv(SPINE_QUALITY_ENV, "hard")
    assert get_spine_quality() == "hard"


def test_unknown_value_falls_back_to_off(monkeypatch):
    """未知の値（typo 等）は安全側の "off" に倒すこと（prompts.py:111-112）。"""
    monkeypatch.setenv(SPINE_QUALITY_ENV, "bogus")
    assert get_spine_quality() == "off"

    monkeypatch.setenv(SPINE_QUALITY_ENV, "HARD ")  # 大文字＋空白
    assert get_spine_quality() == "hard"  # 正規化後は hard


def test_empty_string_falls_back_to_off(monkeypatch):
    """空文字は off に倒すこと。"""
    monkeypatch.setenv(SPINE_QUALITY_ENV, "")
    assert get_spine_quality() == "off"


def test_case_insensitive(monkeypatch):
    """大文字小文字は正規化されること。"""
    monkeypatch.setenv(SPINE_QUALITY_ENV, "Off")
    assert get_spine_quality() == "off"
    monkeypatch.setenv(SPINE_QUALITY_ENV, "SOFT")
    assert get_spine_quality() == "soft"
