"""src/agents/bible.py の単体テスト."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.bible import BibleAgent
from src.agents.orchestrator import AgentContext, AgentName


def _ctx(**artifacts):
    return AgentContext(book_id=1, branch_id=1, ep_num=1, artifacts=artifacts)


async def test_generate_bible_requires_prompt_manager():
    agent = BibleAgent(repo=MagicMock(), llm=MagicMock(), prompt_manager=None)
    with pytest.raises(ValueError, match="PromptManager is required"):
        await agent.generate_bible("t", "s", 3)


async def test_generate_bible_uses_defaults():
    llm = MagicMock()
    llm.generate_json = AsyncMock(return_value={"metadata": {"world": "w"}})
    pm = MagicMock()
    pm.build_world_creation_prompt.return_value = "world prompt"
    agent = BibleAgent(repo=MagicMock(), llm=llm, prompt_manager=pm)
    data = await agent.generate_bible("t", "s", 3)
    assert data == {"world": "w"}
    pm.build_world_creation_prompt.assert_called_once_with(
        genre="fantasy", keywords="", response_schema=None, concept="", target_eps=3
    )


async def test_execute_success():
    llm = MagicMock()
    llm.generate_json = AsyncMock(return_value={"metadata": {"rules": ["r"]}})
    pm = MagicMock()
    pm.build_world_creation_prompt.return_value = "p"
    events: list[str] = []

    agent = BibleAgent(repo=MagicMock(), llm=llm, prompt_manager=pm)
    agent.emit_event = lambda name, payload: events.append(name)

    res = await agent.execute(
        _ctx(title="T", synopsis="S", target_eps=5, concept="C", genre="sf", keywords="k")
    )
    assert res.next_agent == AgentName.CONTEXT_BUILDER
    assert res.artifacts == {"bible": {"rules": ["r"]}}
    assert res.error is None
    assert events == ["bible.started", "bible.completed"]


async def test_execute_missing_title():
    agent = BibleAgent(repo=MagicMock(), llm=MagicMock(), prompt_manager=MagicMock())
    events: list[str] = []
    agent.emit_event = lambda name, payload: events.append(name)
    res = await agent.run(_ctx())
    assert res.error == "title is required in artifacts"
    assert res.next_agent is None
    assert res.artifacts == {}
    assert events == ["bible.started", "bible.error"]


async def test_execute_defaults_when_artifacts_empty_but_title_present():
    llm = MagicMock()
    llm.generate_json = AsyncMock(return_value={"metadata": {}})
    pm = MagicMock()
    pm.build_world_creation_prompt.return_value = "p"
    agent = BibleAgent(repo=MagicMock(), llm=llm, prompt_manager=pm)
    res = await agent.run(_ctx(title="OnlyTitle"))
    assert res.artifacts == {"bible": {}}
    assert pm.build_world_creation_prompt.call_args.kwargs["target_eps"] == 10
