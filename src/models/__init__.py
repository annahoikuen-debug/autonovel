"""AutoNovel ドメインモデル集約エクスポート."""

from __future__ import annotations

from src.models.audit import (
    AuditIssue,
    CausalityAuditResult,
    CausalityLink,
    CriticDirective,
    CriticFeedback,
    DogfeedingReport,
    EasyModeInferenceResult,
    ForeshadowingItem,
    GapAnalysisReport,
    GlobalLogicRepairResult,
    HegemonyAuditResult,
    HegemonyOracleResult,
    ImmersionScore,
    LogicalAuditIssueList,
    LogicalAuditResult,
    NarrativeWavePattern,
    ProducerPlanCandidate,
    StoredAuditIssue,
)
from src.models.base import (
    LLMRequestOptions,
    GenerateResult,
    FlatModelMixin,
)
from src.models.beat_sheet import (
    BeatSheetItem,
    BeatSheet,
    PlotVariantScore,
)
from src.models.bible import (
    StoryDNA,
    MarketingAssets,
    WorldBibleCore,
    WorldBible,
    NovelStructure,
    UltraFastWorldBible,
)
from src.models.character import (
    CharacterConcept,
    CharacterConceptList,
    CharacterRelationship,
    CharacterRegistry,
)
from src.infrastructure.database.models.chunk import ChapterChunk, Vector, HAS_PGVECTOR
from src.models.db import (
    BookDbModel,
    BibleDbModel,
    BranchDbModel,
    CharacterDbModel,
)
from src.models.emotional_hook import (
    EmotionalHookSpec,
)
from src.models.entertainment_check import (
    EntertainmentCheckResult,
)
from src.models.illustration import (
    IllustrationType,
    IllustrationModel,
    SafetyLevel,
    IllustrationRequest,
    IllustrationResult,
)
from src.models.marketing import (
    TitleProposal,
    TitleProposalList,
)
from src.models.narrative_metrics import (
    NarrativeMetricScore,
    NarrativeSceneEvaluation,
)
from src.models.narrative_metrics_db import (
    NarrativeMetric,
    NarrativeMetricDefinition,
)
from src.models.planning_config import (
    PlanningConfig,
)
from src.models.plot import (
    ReviewLog,
    DynamicPacing,
    SceneBeat,
    SceneBeatList,
    CliffhangerDef,
    SceneBeatBlock,
    MasterSceneBlock,
    PlotBlueprintPhase1,
    PlotBlueprintPhase1Batch,
    PlotBlueprintPhase2,
    BaseEngine,
    PlotCoreInfo,
    PlotAnalytics,
    PlotForeshadowing,
    RedHerringItem,
    EnigmaAnalytics,
    ComfortAnalytics,
    CoreEngineMixin,
    EnigmaMixin,
    ComfortMixin,
    SubversionMixin,
    PlotEpisodeBase,
    PlotEpisode,
    MysteryEpisode,
    SliceOfLifeEpisode,
    DramaEpisode,
    RoadmapItem,
    RoadmapList,
    ArcBlueprint,
    ArcList,
    UltraFastPlotBatch,
    PlotDetail,
    CatharsisPattern,
)
from src.models.subversion import (
    SubversionEngine,
    SubversionPattern,
)
from src.models.production_config import (
    NovelProject,
    EpisodeGenerateRequest,
    EpisodeResult,
    ProductionProgress,
)

# PromptVersionDbModel is available via src.backend.database.models (alias of PromptVersion ORM model)
# src.models.prompt_version shim was removed in Q3.
from src.models.report import (
    TokenUsageReport,
    QualityMetricsReport,
    EpisodeSummary,
    ProductionReport,
)
from src.models.sharp_edge import (
    SharpEdgeSpec,
)
from src.models.task import (
    Task,
)
from src.models.world import (
    NarrativeConstraint,
    Foreshadowing,
    ClimaxScene,
    WorldRules,
    AnchorResponse,
    StoryThread,
    WorldState,
    RecoveredItem,
    ForeshadowingAudit,
)
from src.models.editor import (
    SensoryType,
    ToneType,
    AssistAction,
    AssistRequest,
    AssistResponse,
    GraphEvidenceNode,
    AskBibleRequest,
    AskBibleResponse,
    ConsistencyIssue,
    ConsistencyAuditRequest,
    ConsistencyAuditResponse,
    BranchType,
    BeatCard,
    NextBeatsRequest,
    NextBeatsResponse,
)


# src.models.writing のシンボル: writing.py は src.domain.models.plot を eager import するため、
# ここで eager import すると「domain.plot → src.models.__init__ → writing → domain.plot」の
# 循環 import を形成する（モジュール単体 import の入口によっては ImportError）。
# シンボル名はすべて後方互換のため維持する。
_WRITING_LAZY_SYMBOLS = frozenset(
    {
        "EpisodeDraft",
        "CharacterStatusChange",
        "EpisodeMetadata",
        "EpisodeFinalDraft",
        "StyleDNA",
        "StyleFragment",
        "MarketingPack",
        "WritingContext",
        "FullAutoWorkflowResult",
        "PlanGenerationResult",
        "PlotExpansionResult",
        "RetryFailedEpisodesResult",
        "EpisodeWritingResult",
        "PlotRebuildResult",
    }
)


# 後方互換用遅延インポート (ORM循環インポート/起動ブロッキング回避)
def __getattr__(name: str):
    if name in ("Bible", "Book", "Chapter", "Character", "Plot"):
        import src.backend.database.models as _backend_models

        return getattr(_backend_models, name)
    if name in _WRITING_LAZY_SYMBOLS:
        import src.models.writing as _writing

        return getattr(_writing, name)
    if name == "ChapterDbModel":
        # 循環 import 回避: src.domain.models.chapter は src.models.base を import するため、
        # ここで eager import すると「domain → src.models.__init__ → domain」の循環になる。
        from src.domain.models.chapter import ChapterDbModel

        return ChapterDbModel
    if name == "PlotDbModel":
        # 同上: src.domain.models.plot との循環を回避するため遅延解決。
        from src.domain.models.plot import PlotDbModel

        return PlotDbModel
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "ChapterChunk",
    "Vector",
    "HAS_PGVECTOR",
    "Bible",
    "Book",
    "Chapter",
    "Character",
    "Plot",
]
