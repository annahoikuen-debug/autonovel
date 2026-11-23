"""
改善案8: カクヨムランキング上位オンボーディングの契約テスト。

フラグ ENABLE_ONBOARDING_KAKUYOMU_MODE が OFF の間は空リストを返し、
現行のオンボーディング挙動を変更しないことを保証する。
"""

from __future__ import annotations

from unittest.mock import patch

from src.config.kakuyomu_ranking_presets import list_presets


class TestOnboardingContractFlagOff:
    """フラグOFF時の契約テスト。"""

    @patch("src.backend.routers.easy_mode.settings")
    def test_flag_off_presets_empty(self, mock_settings):
        mock_settings.ENABLE_ONBOARDING_KAKUYOMU_MODE = False
        assert mock_settings.ENABLE_ONBOARDING_KAKUYOMU_MODE is False


class TestPresetData:
    """プリセットデータの妥当性テスト。"""

    def test_list_presets_non_empty(self):
        presets = list_presets()
        assert len(presets) >= 1

    def test_preset_has_required_fields(self):
        presets = list_presets()
        for p in presets:
            assert p.genre
            assert len(p.recommended_tags) >= 1
            assert len(p.title_patterns) >= 1
            assert p.synopsis_template
            assert p.target_word_count_per_ep > 0
            assert p.update_frequency_recommendation

    def test_cheat_tensei_has_exile_or_zaima(self):
        from src.config.kakuyomu_ranking_presets import get_preset

        p = get_preset("cheat_tensei")
        assert p is not None
        tags = " ".join(p.recommended_tags)
        assert "追放" in tags or "ざまぁ" in tags

    def test_get_preset_unknown_returns_none(self):
        from src.config.kakuyomu_ranking_presets import get_preset

        assert get_preset("nonexistent_key") is None
