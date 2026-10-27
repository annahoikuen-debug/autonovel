"""src/config/ の各種設定ロード模块の単体テスト。"""
from __future__ import annotations


import yaml

from src.config.billing_plans import (
    PLAN_CONFIG,
    STRIPE_PRICE_TO_PLAN,
    TASK_CREDIT_COSTS,
    get_credits_for_price_id,
    get_tier_for_price_id,
)
from src.config.commercial_beat_sheet import (
    COMMERCIAL_40EP_BEATS,
    get_beat_for_episode,
)
from src.config.emotional_hook_vocabulary import (
    EMOTIONAL_HOOKS,
    get_hook_peak_tension,
    validate_hook,
)
from src.config.env_loader import load_config
from src.config.flaw_and_fetish import FLAW_PRESETS
from src.config.platform_compliance_rules import (
    PLATFORM_COMPLIANCE_RULES,
    PlatformRule,
    get_platform_rule,
)


class TestEnvLoader:
    def test_loads_local_yaml(self, tmp_path, monkeypatch):
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "local.yaml").write_text(
            yaml.safe_dump({"database": {"url": "sqlite://"}}), encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        cfg = load_config()
        assert cfg == {"database": {"url": "sqlite://"}}

    def test_uses_environment_specific_file(self, tmp_path, monkeypatch):
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "local.yaml").write_text("k: local", encoding="utf-8")
        (tmp_path / "config" / "staging.yaml").write_text("k: staging", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ENVIRONMENT", "STAGING")
        assert load_config() == {"k": "staging"}

    def test_falls_back_to_local_when_missing(self, tmp_path, monkeypatch):
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "local.yaml").write_text("k: local", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ENVIRONMENT", "prod")
        assert load_config() == {"k": "local"}


class TestFlawPresets:
    def test_expected_keys(self):
        assert set(FLAW_PRESETS) == {
            "calculating_merchant",
            "twisted_inferiority",
            "paranoia_monopoly",
            "vengeful_grudge",
            "thirst_for_adulation",
            "snobbish_hedonism",
        }

    def test_each_preset_shape(self):
        for name, preset in FLAW_PRESETS.items():
            assert set(preset) == {
                "motive_type", "inner_monologue_sample", "physical_trigger"
            }, name
            assert all(isinstance(v, str) and v for v in preset.values())


class TestBillingPlans:
    def test_get_credits_by_price_id(self):
        assert get_credits_for_price_id("price_pro") == 1200

    def test_get_credits_by_plan_name(self):
        assert get_credits_for_price_id("starter") == 300

    def test_get_credits_unknown(self):
        assert get_credits_for_price_id("nope") == 0

    def test_get_tier_by_price_id(self):
        assert get_tier_for_price_id("price_enterprise") == "enterprise"

    def test_get_tier_by_plan_name(self):
        assert get_tier_for_price_id("pro") == "pro"

    def test_get_tier_unknown_defaults_free(self):
        assert get_tier_for_price_id("nope") == "free"

    def test_tables_consistent(self):
        for tier, cfg in PLAN_CONFIG.items():
            assert STRIPE_PRICE_TO_PLAN[f"price_{tier}"]["tier"] == tier
        for tier in ("starter", "pro", "enterprise"):
            mapped = STRIPE_PRICE_TO_PLAN[f"price_{tier}"]
            assert mapped["monthly_credits"] == PLAN_CONFIG[tier]["monthly_credits"]
        assert TASK_CREDIT_COSTS["writing_standard"] == 10


class TestEmotionalHookVocabulary:
    def test_known_hook(self):
        assert get_hook_peak_tension("catharsis") == 85
        assert validate_hook("catharsis") is True

    def test_unknown_hook(self):
        assert get_hook_peak_tension("nope") == 50
        assert validate_hook("nope") is False

    def test_all_entries_have_three_fields(self):
        for key, (name, desc, peak) in EMOTIONAL_HOOKS.items():
            assert name and desc and isinstance(peak, int), key


class TestCommercialBeatSheet:
    def test_first_beat(self):
        assert get_beat_for_episode(1)["phase"] == COMMERCIAL_40EP_BEATS[0]["phase"]

    def test_midpoint_beat(self):
        assert get_beat_for_episode(20)["phase"] == "Midpoint・大転換"

    def test_out_of_range_falls_back_to_last(self):
        assert get_beat_for_episode(999) is COMMERCIAL_40EP_BEATS[-1]

    def test_ranges_are_ordered(self):
        ranges = [b["range"] for b in COMMERCIAL_40EP_BEATS]
        assert ranges[0][0] == 1
        assert ranges[-1][1] == 40
        for (s1, e1), (s2, _e2) in zip(ranges, ranges[1:]):
            assert e1 + 1 == s2


class TestPlatformComplianceRules:
    def test_all_platforms_present(self):
        assert set(PLATFORM_COMPLIANCE_RULES) == {
            "kakuyomu", "narou", "alphapolis", "kindle"
        }

    def test_get_known_platform(self):
        assert get_platform_rule("NAROU").allowed_ruby_syntax == "kanji(ruby)"

    def test_unknown_platform_falls_back_to_kakuyomu(self):
        assert get_platform_rule("unknown") is PLATFORM_COMPLIANCE_RULES["kakuyomu"]

    def test_platform_rule_defaults(self):
        r = PlatformRule()
        assert r.max_chapter_chars == 100000
        assert r.prohibited_patterns == []
        assert r.notes == ""
