"""
改善案4: タグ最適化配線のユニットテスト。

フラグ ENABLE_TAG_WIRING の ON/OFF による挙動を検証する。
"""

from __future__ import annotations

from unittest.mock import patch

from src.easy_mode.hooks import generate_tag_suggestions


class TestGenerateTagSuggestions:
    """generate_tag_suggestions の挙動テスト。"""

    @patch("src.easy_mode.hooks.settings")
    def test_flag_off_empty(self, mock_settings):
        mock_settings.ENABLE_TAG_WIRING = False
        assert generate_tag_suggestions("HighFantasy") == []

    @patch("src.easy_mode.hooks.settings")
    def test_unknown_genre_empty(self, mock_settings):
        mock_settings.ENABLE_TAG_WIRING = True
        assert generate_tag_suggestions("存在しないジャンルXYZ") == []

    @patch("src.easy_mode.hooks.settings")
    def test_unmapped_preset_key_empty(self, mock_settings):
        mock_settings.ENABLE_TAG_WIRING = True
        # slow_life / loop は意図的にマップしていない（近似マップを避ける方針）
        assert generate_tag_suggestions("SlowLife") == []
        assert generate_tag_suggestions("Mystery") == []

    @patch("src.easy_mode.hooks.settings")
    def test_cheat_tensei_tags(self, mock_settings):
        mock_settings.ENABLE_TAG_WIRING = True
        tags = generate_tag_suggestions("HighFantasy")
        assert len(tags) >= 1
        assert "異世界転生" in tags
        assert "チート" in tags

    @patch("src.easy_mode.hooks.settings")
    def test_zarma_maps_to_cheat_tensei(self, mock_settings):
        mock_settings.ENABLE_TAG_WIRING = True
        tags = generate_tag_suggestions("Zarma")
        assert "異世界転生" in tags
        assert "ざまぁ" in tags

    @patch("src.easy_mode.hooks.settings")
    def test_aku_reijo_maps_to_villainess(self, mock_settings):
        mock_settings.ENABLE_TAG_WIRING = True
        tags = generate_tag_suggestions("AkuReijo")
        assert "悪役令嬢" in tags
        assert "婚約破棄" in tags

    @patch("src.easy_mode.hooks.settings")
    def test_dungeon_admin_maps_to_dungeon_stream(self, mock_settings):
        mock_settings.ENABLE_TAG_WIRING = True
        tags = generate_tag_suggestions("DungeonAdmin")
        assert "ダンジョン" in tags
        assert "配信" in tags

    @patch("src.easy_mode.hooks.settings")
    def test_modern_maps_to_modern_dungeon(self, mock_settings):
        mock_settings.ENABLE_TAG_WIRING = True
        tags = generate_tag_suggestions("Modern")
        assert "現代ダンジョン" in tags
        assert "ハンター" in tags

    @patch("src.easy_mode.hooks.settings")
    def test_keywords_merged(self, mock_settings):
        mock_settings.ENABLE_TAG_WIRING = True
        tags = generate_tag_suggestions("HighFantasy", ["無双", "成り上がり"])
        assert "無双" in tags
        assert "成り上がり" in tags

    @patch("src.easy_mode.hooks.settings")
    def test_keywords_dedup(self, mock_settings):
        mock_settings.ENABLE_TAG_WIRING = True
        # 「チート」は cheat_tensei プリセットの recommended_tags に既に含まれる
        tags = generate_tag_suggestions("HighFantasy", ["チート", "チート"])
        assert tags.count("チート") == 1

    @patch("src.easy_mode.hooks.settings")
    def test_max_10_tags(self, mock_settings):
        mock_settings.ENABLE_TAG_WIRING = True
        many = [f"kw{i}" for i in range(30)]
        tags = generate_tag_suggestions("HighFantasy", many)
        assert len(tags) <= 10

    @patch("src.easy_mode.hooks.settings")
    def test_blank_keywords_ignored(self, mock_settings):
        mock_settings.ENABLE_TAG_WIRING = True
        base = generate_tag_suggestions("HighFantasy")
        tags = generate_tag_suggestions("HighFantasy", ["", "  "])
        assert tags == base
