"""Scene Transition Schemas for Consistency Validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class SceneState:
    """シーンにおけるキャラクター・状況の状態スナップショット"""

    character_name: str
    location: str
    inventory: List[str] = field(default_factory=list)
    status: str = "normal"  # normal, injured, unconscious, etc.
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransitionConflict:
    """検知された矛盾の詳細"""

    conflict_type: str  # location, inventory, status
    message: str
    severity: str = "error"  # error, warning


@dataclass
class TransitionValidationResult:
    """遷移検証結果"""

    is_valid: bool
    conflicts: List[TransitionConflict] = field(default_factory=list)
    patch_suggestions: List[str] = field(default_factory=list)
