"""Unit tests for scene transition schemas."""
from __future__ import annotations

from src.mcp_servers.transition_schemas import (
    SceneState,
    TransitionConflict,
    TransitionValidationResult,
)


def test_transition_schemas_instantiation():
    state = SceneState(
        character_name="Alice",
        location="Forest",
        inventory=["Sword"],
        status="normal"
    )
    assert state.character_name == "Alice"
    assert "Sword" in state.inventory

    conflict = TransitionConflict(conflict_type="location", message="Too far away.", severity="error")
    assert conflict.conflict_type == "location"

    result = TransitionValidationResult(is_valid=False, conflicts=[conflict], patch_suggestions=["Revise travel time."])
    assert result.is_valid is False
    assert len(result.conflicts) == 1
