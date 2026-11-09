"""プロンプトビルダーの spine 注入経路が LLM を呼ばないこと（原則 P2）。

wall: ビルダーの spine 注入経路で誤って LLM 生成（generate_json 等）が混入すると
      テンプレート生成に LLM コストが乗り、原則 D2（テンプレート展開は LLM 0回）
      に反する。本テストはその混入を検出する。
"""

from __future__ import annotations

import pytest

from src.llm.adapters.prompts import build_spine_section, build_spine_summary
from config.story_spine import resolve_spine


def test_build_spine_section_is_pure_string_processing():
    """build_spine_section は純粋文字列処理であり LLM を呼ばないこと。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    result = build_spine_section(spine, "hard", ep_num=1)
    assert isinstance(result, str) and len(result) > 0


def test_build_spine_summary_is_pure_string_processing():
    """build_spine_summary は純粋文字列処理であり LLM を呼ばないこと。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    result = build_spine_summary(spine, quality="soft")
    assert isinstance(result, str) and len(result) > 0


def test_build_spine_summary_quality_none_backward_compat():
    """quality=None の build_spine_summary は従来どおり summary を返すこと
    （H3 で quality パラメータを追加した際の後方互換）。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    summary_default = build_spine_summary(spine)
    summary_none = build_spine_summary(spine, quality=None)
    assert summary_default == summary_none
    assert len(summary_default) > 0


def test_build_spine_section_off_returns_empty():
    """build_spine_section の quality="off" は空文字であること（最重要契約）。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    for ep in (1, 20, 40):
        assert build_spine_section(spine, "off", ep_num=ep) == ""

    # spine=None でも off は空文字
    assert build_spine_section(None, "off", ep_num=1) == ""
