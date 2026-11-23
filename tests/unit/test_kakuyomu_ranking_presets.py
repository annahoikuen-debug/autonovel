"""
改善案8: カクヨムランキング上位オンボーディングプリセットのユニットテスト。
"""

from __future__ import annotations

from src.config.kakuyomu_ranking_presets import get_preset, list_presets


class TestListPresets:
    """list_presets のテスト。"""

    def test_returns_list(self):
        result = list_presets()
        assert isinstance(result, list)

    def test_returns_all_four_presets(self):
        result = list_presets()
        keys = {p.genre for p in result}
        assert "異世界転生" in keys
        assert "悪役令嬢" in keys
        assert "ダンジョン配信" in keys
        assert "現代ダンジョン" in keys

    def test_each_preset_has_valid_fields(self):
        for p in list_presets():
            assert isinstance(p.genre, str) and len(p.genre) > 0
            assert isinstance(p.recommended_tags, list) and len(p.recommended_tags) > 0
            assert isinstance(p.title_patterns, list) and len(p.title_patterns) > 0
            assert isinstance(p.synopsis_template, str) and len(p.synopsis_template) > 0
            assert isinstance(p.target_word_count_per_ep, int) and p.target_word_count_per_ep > 0
            assert isinstance(p.update_frequency_recommendation, str) and len(p.update_frequency_recommendation) > 0


class TestGetPreset:
    """get_preset のテスト。"""

    def test_get_cheat_tensei(self):
        p = get_preset("cheat_tensei")
        assert p is not None
        assert p.genre == "異世界転生"

    def test_get_villainess(self):
        p = get_preset("villainess")
        assert p is not None
        assert p.genre == "悪役令嬢"

    def test_get_dungeon_stream(self):
        p = get_preset("dungeon_stream")
        assert p is not None
        assert p.genre == "ダンジョン配信"

    def test_get_modern_dungeon(self):
        p = get_preset("modern_dungeon")
        assert p is not None
        assert p.genre == "現代ダンジョン"

    def test_get_unknown_returns_none(self):
        assert get_preset("nonexistent") is None
