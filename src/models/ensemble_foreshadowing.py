"""Data models for ensemble foreshadowing resolution judgment."""

from typing import Literal
from pydantic import BaseModel, Field


class EnsembleScoreBreakdown(BaseModel):
    """Detailed score breakdown across the 3 non-LLM ensemble components (+ optional LLM vote)."""

    contract_score: int = Field(
        default=0,
        ge=0,
        le=35,
        description="Beat-sheet contract score (0 or contract-weight points)",
    )
    metadata_score: int = Field(
        default=0,
        ge=0,
        le=40,
        description="LLM writing metadata self-report score (legacy max 40 / mainline 30)",
    )
    syntax_score: int = Field(
        default=0,
        ge=0,
        le=25,
        description="Local syntactic morphology score (legacy max 25 / mainline 20)",
    )
    # PLAN_S1 P3: 任意の LLM 第 4 票 (mainline 時 最大 15 / shadow・off 時 0)
    llm_vote_score: int = Field(
        default=0,
        ge=0,
        le=15,
        description="PLAN_S1 P3: 4th vote from the masked LLM verifier (0 in off/shadow mode)",
    )
    total_score: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Sum of all vote scores (0 to 100 points)",
    )


class EnsembleJudgment(BaseModel):
    """Final ensemble decision for a foreshadowing item without extra LLM invocation."""

    foreshadowing_id: int = Field(
        ...,
        description="ID of the evaluated foreshadowing",
    )
    status: Literal["RESOLVED", "PROGRESSED", "PLANTED"] = Field(
        ...,
        description="Final lifecycle status: RESOLVED (>=75), PROGRESSED (35-74), or PLANTED (<35)",
    )
    score_breakdown: EnsembleScoreBreakdown = Field(
        ...,
        description="Detailed score breakdown",
    )
    rationale: str = Field(
        default="",
        description="Human-readable rationale synthesizing the ensemble decision",
    )
    should_reschedule: bool = Field(
        default=False,
        description="Whether this foreshadowing must be rescheduled for future episodes",
    )
