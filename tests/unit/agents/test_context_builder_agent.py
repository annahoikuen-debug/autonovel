"""Tests for src/agents/context_builder_agent.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.context_builder_agent import (
    ContextBuilderAgent,
    resolve_character_flaw,
)
from src.agents.orchestrator import AgentContext, AgentName


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_repo():
    """Mock repository."""
    repo = MagicMock()
    repo.session = MagicMock()
    return repo


@pytest.fixture
def mock_llm():
    """Mock LLM."""
    return MagicMock()


@pytest.fixture
def mock_style_rag():
    """Mock style RAG."""
    return MagicMock()


@pytest.fixture
def mock_rag_prefetch():
    """Mock RAG prefetch."""
    return MagicMock()


@pytest.fixture
def mock_event_bus():
    """Mock event bus."""
    return MagicMock()


@pytest.fixture
def mock_reflective_rag():
    """Mock reflective RAG."""
    return MagicMock()


@pytest.fixture
def mock_compressor():
    """Mock compressor."""
    return MagicMock()


@pytest.fixture
def mock_social_manager():
    """Mock social manager."""
    return MagicMock()


@pytest.fixture
def mock_age_client():
    """Mock age client."""
    return MagicMock()


@pytest.fixture
def context_builder_agent(
    mock_repo,
    mock_llm,
    mock_style_rag,
    mock_rag_prefetch,
    mock_event_bus,
    mock_reflective_rag,
    mock_compressor,
    mock_social_manager,
    mock_age_client,
):
    """ContextBuilderAgent instance with mocked dependencies."""
    return ContextBuilderAgent(
        repo=mock_repo,
        llm=mock_llm,
        style_rag=mock_style_rag,
        rag_prefetch=mock_rag_prefetch,
        event_bus=mock_event_bus,
        reflective_rag=mock_reflective_rag,
        compressor=mock_compressor,
        social_manager=mock_social_manager,
        age_client=mock_age_client,
    )


@pytest.fixture
def sample_agent_context():
    """Sample agent context."""
    return AgentContext(
        book_id=1,
        ep_num=1,
        branch_id=1,
        artifacts={
            "repo": MagicMock(),  # will be replaced in tests
            "target_word_count": 3000,
            "style_tag": None,
        },
    )


# ---------------------------------------------------------------------------
# Unit tests for resolve_character_flaw (helper function)
# ---------------------------------------------------------------------------


def test_resolve_character_flaw_existing_flaw_dict():
    """resolve_character_flaw uses existing flaw dict if provided."""
    char_data = {
        "name": "テストキャラ",
        "personality": "優しい",
        "secret_flaw": {
            "motive_type": "金銭欲",
            "inner_monologue_sample": "お金が欲しい。",
            "physical_trigger": "目を光らせる",
        },
        "target_of_contempt": "ライバル",
    }
    result = resolve_character_flaw(char_data)
    # Check that the result is a CharacterFlawProfile (we can check attributes)
    assert result.character_name == "テストキャラ"
    assert result.surface_persona == "優しい"
    assert result.secret_flaw.motive_type == "金銭欲"
    assert result.secret_flaw.inner_monologue_sample == "お金が欲しい。"
    assert result.secret_flaw.physical_trigger == "目を光らせる"
    assert result.target_of_contempt == "ライバル"


def test_resolve_character_flaw_existing_flaw_object():
    """resolve_character_flaw uses existing SecretMotif object."""
    from src.models.character_flaw import SecretMotive

    existing_flaw = SecretMotive(
        motive_type="プライド",
        inner_monologue_sample="プライドが高い。",
        physical_trigger="胸を張る",
    )
    char_data = {
        "name": "テストキャラ2",
        "personality": "クール",
        "secret_flaw": existing_flaw,
        "target_of_contempt": "敵",
    }
    result = resolve_character_flaw(char_data)
    assert result.character_name == "テストキャラ2"
    assert result.surface_persona == "クール"
    assert result.secret_flaw is existing_flaw  # same object
    assert result.target_of_contempt == "敵"


def test_resolve_character_flaw_preset_vengeful():
    """resolve_character_flaw applies vengeful preset when keywords present."""
    char_data = {
        "name": "復讐者",
        "personality": "暗い",
        # no secret_flaw, and no target_of_contempt key to get default
    }
    result = resolve_character_flaw(char_data)
    assert result.character_name == "復讐者"
    assert result.surface_persona == "暗い"
    from src.config.flaw_and_fetish import FLAW_PRESETS

    preset = FLAW_PRESETS["vengeful_grudge"]
    assert result.secret_flaw.motive_type == preset["motive_type"]
    assert result.secret_flaw.inner_monologue_sample == preset["inner_monologue_sample"]
    assert result.secret_flaw.physical_trigger == preset["physical_trigger"]
    assert result.target_of_contempt == "かつて主人公を見下した旧勢力"


def test_resolve_character_flaw_preset_inferiority():
    """resolve_character_flaw applies twisted_inferiority preset."""
    char_data = {
        "name": "劣等感の塊",
        "personality": "内向的",
        # no secret_flaw, and no target_of_contempt key to get default
    }
    result = resolve_character_flaw(char_data)
    assert result.character_name == "劣等感の塊"
    assert result.surface_persona == "内向的"
    from src.config.flaw_and_fetish import FLAW_PRESETS

    preset = FLAW_PRESETS["twisted_inferiority"]
    assert result.secret_flaw.motive_type == preset["motive_type"]
    assert result.secret_flaw.inner_monologue_sample == preset["inner_monologue_sample"]
    assert result.secret_flaw.physical_trigger == preset["physical_trigger"]
    assert result.target_of_contempt == "かつて主人公を見下した旧勢力"


def test_resolve_character_flaw_default_preset():
    """resolve_character_flaw uses default preset when no keywords."""
    char_data = {
        "name": "普通のキャラ",
        "personality": "普通",
        # no secret_flaw, and no target_of_contempt key to get default
    }
    result = resolve_character_flaw(char_data)
    assert result.character_name == "普通のキャラ"
    assert result.surface_persona == "普通"
    from src.config.flaw_and_fetish import FLAW_PRESETS

    preset = FLAW_PRESETS["calculating_merchant"]
    assert result.secret_flaw.motive_type == preset["motive_type"]
    assert result.secret_flaw.inner_monologue_sample == preset["inner_monologue_sample"]
    assert result.secret_flaw.physical_trigger == preset["physical_trigger"]
    assert result.target_of_contempt == "かつて主人公を見下した旧勢力"


# ---------------------------------------------------------------------------
# Tests for ContextBuilderAgent methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_missing_repo(context_builder_agent):
    """execute returns error when repo is missing."""
    ctx = AgentContext(
        book_id=1,
        ep_num=1,
        branch_id=1,
        artifacts={},  # no repo
    )
    result = await context_builder_agent.execute(ctx)
    assert result.error is not None
    assert "repo is required in artifacts" in result.error
    assert result.artifacts == {}


@pytest.mark.asyncio
async def test_execute_success(context_builder_agent, mock_repo):
    """execute returns success when all required artifacts are present."""
    # We'll mock the internal _build_full_writing_context_internal to return a dummy context
    mock_context = {"plot": {"detailed_blueprint": "dummy plot"}, "target_word_count": 3000}
    with patch.object(
        context_builder_agent,
        "_build_full_writing_context_internal",
        AsyncMock(return_value=mock_context),
    ):
        ctx = AgentContext(
            book_id=1,
            ep_num=1,
            branch_id=1,
            artifacts={"repo": mock_repo, "target_word_count": 3000, "style_tag": None},
        )
        result = await context_builder_agent.execute(ctx)

    assert result.error is None
    assert result.artifacts["writing_context"] == mock_context
    assert result.next_agent == AgentName.WRITING


def test_allocate_token_budgets_default(context_builder_agent):
    """allocate_token_budgets returns correct ratios for general scene."""
    result = context_builder_agent.allocate_token_budgets(total_budget=4000)
    # general scene -> rag_ratio = 0.40
    assert result["rag_budget"] == 1600
    assert result["compression_budget"] == 2400


def test_allocate_token_budgets_scene_types(context_builder_agent):
    """allocate_token_budgets adjusts ratio based on scene type."""
    test_cases = [
        (("mystery", 0.55), 4000, 2200, 1800),
        (("political", 0.55), 4000, 2200, 1800),
        (("flashback", 0.55), 4000, 2200, 1800),
        (("romance", 0.25), 4000, 1000, 3000),
        (("daily", 0.25), 4000, 1000, 3000),
        (("combat", 0.30), 4000, 1200, 2800),
        (("survival", 0.30), 4000, 1200, 2800),
    ]
    for (scene_type, expected_rag_ratio), total, expected_rag, expected_comp in test_cases:
        result = context_builder_agent.allocate_token_budgets(total_budget=total, scene_type=scene_type)
        assert result["rag_budget"] == expected_rag, f"Failed for scene_type {scene_type}"
        assert result["compression_budget"] == expected_comp, f"Failed for scene_type {scene_type}"


# ---------------------------------------------------------------------------
# Tests for build_context method
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_context_basic(context_builder_agent):
    """build_context returns a dictionary with the provided data."""
    bible_data = {"world_name": "テスト世界", "rules": ["魔法がある"]}
    characters = [{"name": "主人公", "role": "主人公"}]
    prev_summary = "前話のあらすじ"
    result = await context_builder_agent.build_context(
        book_id=1,
        episode_number=5,
        bible_data=bible_data,
        characters=characters,
        prev_summary=prev_summary,
    )
    assert result["book_id"] == 1
    assert result["episode_number"] == 5
    assert result["bible_data"] == bible_data
    assert result["characters"] == characters
    assert result["prev_summary"] == prev_summary
    assert result["world_name"] == "テスト世界"
    assert result["rules"] == ["魔法がある"]
    assert result["character_names"] == ["主人公"]


# ---------------------------------------------------------------------------
# Additional tests for internal methods can be added as needed to increase coverage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
