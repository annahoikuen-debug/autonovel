"""TRACK-C C2: 監査モデル階層化 (tier ルーティング) の単体テスト。

事実性・構造・一貫性などの「機械的判定」監査は tier1(安価モデル)に
ルーティングされ、クリエイティブ・感情などは tier2(通常モデル)が
維持されることを検証する。
"""

from unittest.mock import MagicMock

from src.services.audit.service import (
    AUDIT_TIER_MODELS,
    AuditService,
    AuditTierRouter,
    OPENROUTER_ROUTING,
)


class TestOpenRouterRoutingConfig:
    """OPENROUTER_ROUTING / モデル割当設定が正しく定義されていること。"""

    def test_factual_and_structure_are_tier1(self):
        assert OPENROUTER_ROUTING["factual"] == "tier1"
        assert OPENROUTER_ROUTING["structure"] == "tier1"
        assert OPENROUTER_ROUTING["consistency"] == "tier1"

    def test_creative_and_emotion_are_tier2(self):
        assert OPENROUTER_ROUTING["creativity"] == "tier2"
        assert OPENROUTER_ROUTING["emotion"] == "tier2"
        assert OPENROUTER_ROUTING["reader_hook"] == "tier2"
        assert OPENROUTER_ROUTING["deai"] == "tier2"

    def test_tier_models_are_assigned(self):
        assert AUDIT_TIER_MODELS["tier1"] == "google/gemini-1.5-flash"
        assert AUDIT_TIER_MODELS["tier2"] == "anthropic/claude-3-5-sonnet-20241022"
        assert AUDIT_TIER_MODELS["tier1"] != AUDIT_TIER_MODELS["tier2"]


class TestAuditTierRouter:
    """AuditTierRouter による監査タイプ -> ティア解決。"""

    def setup_method(self):
        self.router = AuditTierRouter()

    def test_factual_routes_to_cheap_tier(self):
        assert self.router.tier_for("factual") == "tier1"
        assert self.router.is_cheap_tier("factual") is True

    def test_structure_routes_to_cheap_tier(self):
        assert self.router.tier_for("structure") == "tier1"
        assert self.router.is_cheap_tier("structure") is True

    def test_consistency_routes_to_cheap_tier(self):
        assert self.router.tier_for("consistency") == "tier1"
        assert self.router.is_cheap_tier("consistency") is True

    def test_creative_and_emotion_stay_on_normal_tier(self):
        assert self.router.tier_for("creativity") == "tier2"
        assert self.router.tier_for("emotion") == "tier2"
        assert self.router.tier_for("reader_hook") == "tier2"
        assert self.router.tier_for("deai") == "tier2"
        assert self.router.is_cheap_tier("creativity") is False

    def test_unknown_audit_type_falls_back_to_tier2(self):
        assert self.router.tier_for("unknown_audit") == "tier2"
        assert self.router.is_cheap_tier("unknown_audit") is False

    def test_model_assignment_applied_per_audit_type(self):
        assert self.router.model_for("factual") == AUDIT_TIER_MODELS["tier1"]
        assert self.router.model_for("structure") == AUDIT_TIER_MODELS["tier1"]
        assert self.router.model_for("creativity") == AUDIT_TIER_MODELS["tier2"]
        assert self.router.model_for("emotion") == AUDIT_TIER_MODELS["tier2"]

    def test_custom_routing_overrides_default(self):
        custom_router = AuditTierRouter(routing={"factual": "tier2", "creativity": "tier1"})
        assert custom_router.tier_for("factual") == "tier2"
        assert custom_router.tier_for("creativity") == "tier1"
        # 未設定のキーはデフォルト (tier2) にフォールバック
        assert custom_router.tier_for("structure") == "tier2"
        assert custom_router.is_cheap_tier("factual") is False
        assert custom_router.is_cheap_tier("creativity") is True


class TestAuditServiceTierRouting:
    """AuditService がティア別モデル割当を適用して初期化されること。"""

    def test_factual_and_structure_auditors_use_cheap_llm(self):
        normal_llm = MagicMock()
        cheap_llm = MagicMock()
        prompt_manager = MagicMock()

        service = AuditService(
            llm=normal_llm,
            prompt_manager=prompt_manager,
            cheap_llm=cheap_llm,
        )

        # 構造監査 (screen_plot) と一貫性監査 (audit_ability) は安価 tier1 モデル
        assert service.fast_screener.llm is cheap_llm
        assert service.ability_checker.llm is cheap_llm
        # AI感除去 (audit_deai) は通常モデルを維持
        assert service.deai_auditor.llm is normal_llm
        # ルーター経由でも解決できる
        assert service.router.tier_for("structure") == "tier1"
        assert service.router.tier_for("deai") == "tier2"

    def test_without_cheap_llm_falls_back_to_normal_llm(self):
        normal_llm = MagicMock()
        service = AuditService(llm=normal_llm, prompt_manager=MagicMock())

        assert service.cheap_llm is normal_llm
        assert service.fast_screener.llm is normal_llm
        assert service.ability_checker.llm is normal_llm
        assert service.deai_auditor.llm is normal_llm
