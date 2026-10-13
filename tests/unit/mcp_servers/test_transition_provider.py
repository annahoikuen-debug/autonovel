"""Unit tests for SceneTransitionValidator."""
from __future__ import annotations

from src.mcp_servers.transition_schemas import SceneState
from src.mcp_servers.providers.transition_provider import SceneTransitionValidator


def test_transition_validator_valid():
    validator = SceneTransitionValidator()
    from_st = SceneState(character_name="Alice", location="Forest", inventory=["Sword"], status="normal")
    to_st = SceneState(character_name="Alice", location="Forest", inventory=["Sword"], status="normal")

    res = validator.validate_transition(from_st, to_st)
    assert res.is_valid is True
    assert len(res.conflicts) == 0


def test_transition_validator_location_conflict():
    validator = SceneTransitionValidator()
    from_st = SceneState(character_name="Alice", location="Dungeon")
    to_st = SceneState(character_name="Alice", location="Royal Castle")

    res = validator.validate_transition(from_st, to_st)
    assert res.is_valid is False
    assert any(c.conflict_type == "location" for c in res.conflicts)
    assert len(res.patch_suggestions) > 0


def test_transition_validator_inventory_conflict():
    validator = SceneTransitionValidator()
    from_st = SceneState(character_name="Bob", location="Town", inventory=[])
    to_st = SceneState(character_name="Bob", location="Town", inventory=["Legendary Staff"])

    res = validator.validate_transition(from_st, to_st)
    # Warning severity doesn't invalidate is_valid directly unless error, but triggers conflict
    assert any(c.conflict_type == "inventory" for c in res.conflicts)


def test_transition_validator_status_conflict():
    validator = SceneTransitionValidator()
    from_st = SceneState(character_name="Charlie", location="Camp", status="critical_injured")
    to_st = SceneState(character_name="Charlie", location="Camp", status="normal")

    res = validator.validate_transition(from_st, to_st)
    assert res.is_valid is False
    assert any(c.conflict_type == "status" for c in res.conflicts)
