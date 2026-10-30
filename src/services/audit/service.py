import logging
from typing import Any

from src.agents.audit import AbilityConsistencyChecker, DeAIAuditor, FastPlotScreener
from config.erotic_thresholds import MAX_CONSECUTIVE_PEAK_EPISODES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TRACK-C (C2): 監査モデル階層化ルーティング設定
#
# 事実性・構造・一貫性など「機械的判定」が中心の監査は tier1（安価モデル）
# にルーティングし、クリエイティブ・感情・読者体験など「創作判断」が
# 必要な監査は tier2（通常モデル）を維持することで LLM コストを最適化する。
#
# OPENROUTER_ROUTING: 監査タイプ -> モデルティア (tier1/tier2)
# AUDIT_TIER_MODELS:   モデルティア -> OpenRouter モデル名
# ---------------------------------------------------------------------------

OPENROUTER_ROUTING: dict[str, str] = {
    "factual": "tier1",        # 事実性監査（事実・固有名詞・因果の機械的検証）
    "structure": "tier1",      # 構造監査（プロット構造・形式チェック）
    "consistency": "tier1",    # 一貫性監査（能力・設定整合性の機械的チェック）
    "creativity": "tier2",     # クリエイティブ監査（通常モデルを維持）
    "emotion": "tier2",        # 感情・読者体験監査（通常モデルを維持）
    "reader_hook": "tier2",    # フック・感情曲線監査（通常モデルを維持）
    "deai": "tier2",           # AI感除去監査（通常モデルを維持）
}

AUDIT_TIER_MODELS: dict[str, str] = {
    "tier1": "google/gemini-1.5-flash",            # 安価 tier1（機械的判定向け）
    "tier2": "anthropic/claude-3-5-sonnet-20241022",  # 通常 tier2（創作判断向け）
}

DEFAULT_TIER = "tier2"


class AuditTierRouter:
    """監査タイプをモデルティア（および OpenRouter モデル名）に解決するルーター。"""

    def __init__(self, routing: dict[str, str] | None = None) -> None:
        self.routing = dict(routing or OPENROUTER_ROUTING)

    def tier_for(self, audit_type: str) -> str:
        """監査タイプに対応するモデルティアを返す。"""
        return self.routing.get(audit_type, DEFAULT_TIER)

    def model_for(
        self, audit_type: str, tier_models: dict[str, str] | None = None
    ) -> str:
        """監査タイプに対応する OpenRouter モデル名を返す。"""
        tier = self.tier_for(audit_type)
        models = tier_models or AUDIT_TIER_MODELS
        return models.get(tier, models[DEFAULT_TIER])

    def is_cheap_tier(self, audit_type: str) -> bool:
        """監査タイプが tier1（安価モデル）対象かを返す。"""
        return self.tier_for(audit_type) == "tier1"


class AuditService:
    """監査サービス"""

    def __init__(
        self,
        llm: Any,
        prompt_manager: Any,
        cheap_llm: Any = None,
        router: AuditTierRouter | None = None,
    ):
        self.normal_llm = llm
        # tier1 監査に使用する安価モデル。未指定時は通常モデルでフォールバック。
        self.cheap_llm = cheap_llm if cheap_llm is not None else llm
        self.prompt_manager = prompt_manager
        self.router = router or AuditTierRouter()
        # ティア別モデル割当を適用して各監査エージェントを初期化
        self.fast_screener = self._build_screener("structure")
        self.ability_checker = self._build_checker("consistency")
        self.deai_auditor = self._build_deai("deai")

    # ------------------------------------------------------------------
    # ティア別モデル割当の内部ファクトリ
    # ------------------------------------------------------------------

    def _llm_for(self, audit_type: str) -> Any:
        """監査タイプに応じて tier1(安価) か通常 LLM を返す。"""
        return self.cheap_llm if self.router.is_cheap_tier(audit_type) else self.normal_llm

    def _build_screener(self, audit_type: str) -> FastPlotScreener:
        return FastPlotScreener(llm=self._llm_for(audit_type), prompt_manager=self.prompt_manager)

    def _build_checker(self, audit_type: str) -> AbilityConsistencyChecker:
        return AbilityConsistencyChecker(
            llm=self._llm_for(audit_type), prompt_manager=self.prompt_manager
        )

    def _build_deai(self, audit_type: str) -> DeAIAuditor:
        return DeAIAuditor(llm=self._llm_for(audit_type), prompt_manager=self.prompt_manager)

    async def screen_plot(self, blueprint: str) -> tuple[bool, str]:
        return await self.fast_screener.screen_plot(blueprint)

    async def audit_ability(
        self, blueprint: str, settings_json: str, characters_json: str
    ) -> tuple[bool, str, str]:
        return await self.ability_checker.audit_ability_consistency(
            blueprint, settings_json, characters_json
        )

    async def audit_deai(self, content: str) -> tuple[bool, str]:
        return await self.deai_auditor.audit(content)

    def get_erotic_advice(
        self, intensities: list[int], current_ep: int, total_eps: int
    ) -> list[str]:
        """官能シーンのタイミングに関するAIアドバイスを返す。"""
        advice = []

        if len(intensities) >= MAX_CONSECUTIVE_PEAK_EPISODES:
            recent = intensities[-MAX_CONSECUTIVE_PEAK_EPISODES:]
            if all(i >= 4 for i in recent):
                advice.append(
                    "⚠️ 連続するピークシーンが多すぎます。読者疲労の可能性があります。次の1〜2話はクールダウンを推奨します。"
                )

        if intensities:
            avg = sum(intensities) / len(intensities)
            if avg > 3.5:
                advice.append(
                    "⚠️ 全体の官能強度の平均が高めです。情緒的な「溜め」の回を増やすことを検討してください。"
                )

        return advice
