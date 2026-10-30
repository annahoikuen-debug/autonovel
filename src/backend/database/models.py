"""Database models (shim for backward compatibility).

TRACK-A5: ORM モデル実体は src/infrastructure/database/models/ に移動。
本モジュールは後方互換のための再エクスポート shim として機能する。
"""

from __future__ import annotations

from sqlalchemy import event, text

from src.infrastructure.database.models.base_orm import Base
from src.backend.database.models_checkpoint import WorkflowCheckpointModel

# 0000_initial_migration の `Base.metadata.create_all` が全テーブルを確実に作るため、
# 別モジュールに定義されたモデルもここで import して同一の Base に登録する。
# （未 import のままだと credit_transactions / subscriptions / stripe_webhook_events /
#   foreshadowings / character_relations / episode_digests が create_all 実行時にも
#   存在せず、差分が Alembic autogenerate にしか現れない。）
from src.backend.database.models_billing import (  # noqa: F401
    CreditTransaction,
    StripeWebhookEvent,
    Subscription,
)
from src.backend.database.models_digest import EpisodeDigestModel  # noqa: F401
from src.backend.database.models_foreshadowing import ForeshadowingModel  # noqa: F401
from src.backend.database.models_relation import CharacterRelationModel  # noqa: F401
# users.tenant_id / books.tenant_id が FK 参照する `tenants` テーブルを
# metadata に登録する。未 import だと NoReferencedTableError になる。
from src.backend.database.models_tenant import Tenant, TenantMember  # noqa: F401

# TRACK-A5: ORM モデル実体は src/infrastructure/database/models/ に移動。
# 下記は後方互換のための再エクスポート（`from src.backend.database.models import X` が
# 従来どおり動作するためのエイリアス）。
from src.infrastructure.database.models import (  # noqa: F401
    AudioAssetModel,
    AuditIssue,
    BackgroundTask,
    Bible,
    BiblePendingSetting,
    Book,
    Branch,
    BranchPlaySession,
    Chapter,
    ChapterVersion,
    Character,
    CharacterArc,
    CharacterComment,
    CharacterJournal,
    CharacterRelationship,
    Comment,
    CostLogModel,
    CostRecord,
    CustomStyle,
    EasyModeDraft,
    EntertainmentCheckLog,
    Foreshadowing,
    GenerationRun,
    Illustration,
    InternalState,
    Masterpiece,
    MultimediaArtifact,
    MultimediaTask,
    NarrativeMetric,
    OptimizationHistory,
    Outbox,
    PatchReview,
    PatchReviewStatus,
    PendingPatch,
    Plot,
    PDCAHistorySnapshot,
    ProjectMember,
    PromptUsageLog,
    PromptVersion,
    PublicationScheduleModel,
    RelationshipHistory,
    Rule,
    SafeDateTime,
    SettingDelta,
    SettingVersion,
    StyleFragment,
    Task,
    TaskWALLogModel,
    User,
    UserPreference,
)

# 後方互換性用エイリアス（旧 src.backend.database.models.X 経路でアクセス可能にするため）
BibleDbModel = Bible
BookDbModel = Book
BranchDbModel = Branch
ChapterDbModel = Chapter
CharacterDbModel = Character
CharacterRelationshipDbModel = CharacterRelationship
CharacterJournalDbModel = CharacterJournal
CharacterCommentDbModel = CharacterComment
RelationshipHistoryDbModel = RelationshipHistory
PublicationScheduleDbModel = PublicationScheduleModel
PlotDbModel = Plot
PromptVersionDbModel = PromptVersion
WorldBible = Bible
PDCAHistorySnapshotDbModel = PDCAHistorySnapshot
AudioAssetDbModel = AudioAssetModel


# Engine event listener for SQLite WAL mode (applied in core.py via DatabaseManager)
@event.listens_for(Base.metadata, "after_create")
def on_create(target, connection, **kw):
    if "sqlite" in str(connection.engine.name):
        connection.execute(text("PRAGMA journal_mode=WAL;"))
        connection.execute(text("PRAGMA foreign_keys=ON;"))


__all__ = [
    "User",
    "Book",
    "UserPreference",
    "Branch",
    "BranchPlaySession",
    "Bible",
    "BiblePendingSetting",
    "Plot",
    "Chapter",
    "Character",
    "CharacterArc",
    "Foreshadowing",
    "Outbox",
    "PromptVersion",
    "PromptUsageLog",
    "Rule",
    "Masterpiece",
    "AuditIssue",
    "PatchReview",
    "SettingDelta",
    "SettingVersion",
    "OptimizationHistory",
    "StyleFragment",
    "CustomStyle",
    "InternalState",
    "PendingPatch",
    "BackgroundTask",
    "NarrativeMetric",
    "EntertainmentCheckLog",
    "CostRecord",
    "CostLogModel",
    "GenerationRun",
    "TaskWALLogModel",
    "ProjectMember",
    "Comment",
    "ChapterVersion",
    "Illustration",
    "EasyModeDraft",
    "MultimediaArtifact",
    "MultimediaTask",
    "CharacterRelationship",
    "CharacterJournal",
    "CharacterComment",
    "RelationshipHistory",
    "PublicationScheduleModel",
    "PDCAHistorySnapshot",
    "AudioAssetModel",
    "WorkflowCheckpointModel",
    # 後方互換エイリアス
    "BibleDbModel",
    "BookDbModel",
    "BranchDbModel",
    "ChapterDbModel",
    "CharacterDbModel",
    "CharacterRelationshipDbModel",
    "CharacterJournalDbModel",
    "CharacterCommentDbModel",
    "RelationshipHistoryDbModel",
    "PublicationScheduleDbModel",
    "PlotDbModel",
    "PromptVersionDbModel",
    "WorldBible",
    "PDCAHistorySnapshotDbModel",
    "AudioAssetDbModel",
]
