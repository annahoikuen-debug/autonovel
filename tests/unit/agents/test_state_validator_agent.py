"""src/agents/state_validator.py の単体テスト."""

from __future__ import annotations

import pytest

from src.agents.state_validator import (
    CharacterStatusChange,
    EpisodeStatusChanges,
    StateContradictionError,
    StateValidator,
    StateValidatorAgent,
)


def test_state_change_dataclasses():
    csc = CharacterStatusChange("ch1", "hp", 10, 5)
    assert csc.character_id == "ch1"
    assert csc.attribute == "hp"
    assert csc.old_value == 10
    assert csc.new_value == 5

    esc = EpisodeStatusChanges([csc])
    assert esc.character_status_changes == [csc]


def test_state_contradiction_error_is_exception():
    assert issubclass(StateContradictionError, Exception)
    with pytest.raises(StateContradictionError):
        raise StateContradictionError("boom")


def test_validate_transitions_returns_none():
    assert StateValidator.validate_transitions({}, []) is None


async def test_state_validator_agent_reports_all_issues():
    agent = StateValidatorAgent()
    assert agent.name == "state_validator"
    issues = await agent.validate({})
    assert "APIキーが未設定です。" in issues
    assert any("app_mode が不正です" in i for i in issues)


async def test_state_validator_agent_valid_state():
    agent = StateValidatorAgent()
    assert await agent.validate({"api_key": "k", "app_mode": "easy"}) == []
    assert await agent.validate({"api_key": "k", "app_mode": "advanced"}) == []
