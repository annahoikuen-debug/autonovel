"""Infrastructure ORM models package."""

from __future__ import annotations

from src.infrastructure.database.models.base_orm import Base, BaseDbModel
from src.infrastructure.database.models.book import Book
from src.infrastructure.database.models.chunk import ChapterChunk
from src.infrastructure.database.models.task import Task
from src.infrastructure.database.models.publish_record import PublishRecord
from src.infrastructure.database.models.book_score import BookScore
from src.infrastructure.database.models.user import User
from src.infrastructure.database.models.user_preference import UserPreference
from src.infrastructure.database.models.branch import Branch
from src.infrastructure.database.models.branch_play_session import BranchPlaySession
from src.infrastructure.database.models.safe_datetime import SafeDateTime
from src.infrastructure.database.models.bible import Bible
from src.infrastructure.database.models.bible_pending_setting import BiblePendingSetting
from src.infrastructure.database.models.plot import Plot
from src.infrastructure.database.models.chapter import Chapter
from src.infrastructure.database.models.character import Character
from src.infrastructure.database.models.character_arc import CharacterArc
from src.infrastructure.database.models.foreshadowing import Foreshadowing
from src.infrastructure.database.models.outbox import Outbox
from src.infrastructure.database.models.prompt_version import PromptVersion
from src.infrastructure.database.models.prompt_usage_log import PromptUsageLog
from src.infrastructure.database.models.rule import Rule
from src.infrastructure.database.models.masterpiece import Masterpiece
from src.infrastructure.database.models.audit_issue import AuditIssue
from src.infrastructure.database.models.patch_review_status import PatchReviewStatus
from src.infrastructure.database.models.patch_review import PatchReview
from src.infrastructure.database.models.setting_delta import SettingDelta
from src.infrastructure.database.models.setting_version import SettingVersion
from src.infrastructure.database.models.optimization_history import OptimizationHistory
from src.infrastructure.database.models.style_fragment import StyleFragment
from src.infrastructure.database.models.custom_style import CustomStyle
from src.infrastructure.database.models.internal_state import InternalState
from src.infrastructure.database.models.pending_patch import PendingPatch
from src.infrastructure.database.models.background_task import BackgroundTask
from src.infrastructure.database.models.narrative_metric import NarrativeMetric
from src.infrastructure.database.models.entertainment_check_log import (
    EntertainmentCheckLog,
)
from src.infrastructure.database.models.cost_record import CostRecord
from src.infrastructure.database.models.cost_log_model import CostLogModel
from src.infrastructure.database.models.generation_run import GenerationRun
from src.infrastructure.database.models.task_wal_log_model import TaskWALLogModel
from src.infrastructure.database.models.project_member import ProjectMember
from src.infrastructure.database.models.comment import Comment
from src.infrastructure.database.models.chapter_version import ChapterVersion
from src.infrastructure.database.models.illustration import Illustration
from src.infrastructure.database.models.easy_mode_draft import EasyModeDraft
from src.infrastructure.database.models.multimedia_artifact import MultimediaArtifact
from src.infrastructure.database.models.multimedia_task import MultimediaTask
from src.infrastructure.database.models.character_relationship import (
    CharacterRelationship,
)
from src.infrastructure.database.models.character_journal import CharacterJournal
from src.infrastructure.database.models.character_comment import CharacterComment
from src.infrastructure.database.models.relationship_history import (
    RelationshipHistory,
)
from src.infrastructure.database.models.publication_schedule_model import (
    PublicationScheduleModel,
)
from src.infrastructure.database.models.pdca_history_snapshot import (
    PDCAHistorySnapshot,
)
from src.infrastructure.database.models.audio_asset_model import AudioAssetModel
from src.infrastructure.database.models.foreshadowing_model import ForeshadowingModel
from src.infrastructure.database.models.workflow_checkpoint import WorkflowCheckpointModel

__all__ = [
    "Base",
    "BaseDbModel",
    "Book",
    "ChapterChunk",
    "Task",
    "PublishRecord",
    "BookScore",
    "User",
    "UserPreference",
    "Branch",
    "BranchPlaySession",
    "SafeDateTime",
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
    "PatchReviewStatus",
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
    "ForeshadowingModel",
    "WorkflowCheckpointModel",
]
