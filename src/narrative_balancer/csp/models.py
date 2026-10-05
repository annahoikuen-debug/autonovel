"""Domain models, enums and structures for CSP Narrative Balancer."""

from enum import Enum
from typing import List
from pydantic import BaseModel, Field, ConfigDict

# CSP 固有の型ではないが、CSP パッケージの公開モデル面の一部として
# 従来から `csp.models` 経由で参照されていた共通モデルを再輸出する
# (`tests/unit/test_csp_models.py` が `from ...csp.models import BeatType` を使う)。
# 定義は上位パッケージの共通モデルにある。
from src.narrative_balancer.models import BeatType  # noqa: F401  (再輸出)

__all__ = [
    "CharRole",
    "ConstraintPriority",
    "ConflictClause",
    "BeatType",
]


class CharRole(str, Enum):
    """Character narrative roles."""
    PROTAGONIST = "PROTAGONIST"
    RIVAL = "RIVAL"
    MENTOR = "MENTOR"
    ALLY = "ALLY"
    ANTAGONIST = "ANTAGONIST"


class ConstraintPriority(str, Enum):
    """Constraint enforcement level."""
    HARD = "HARD"
    SOFT_HIGH = "SOFT_HIGH"
    SOFT_MEDIUM = "SOFT_MEDIUM"
    SOFT_LOW = "SOFT_LOW"


class ConflictClause(BaseModel):
    """Diagnosed conflicting constraint clause in infeasible problems."""
    model_config = ConfigDict(extra="ignore")

    constraint_name: str
    episodes: List[int] = Field(default_factory=list)
    description: str
    suggested_relaxation: str
