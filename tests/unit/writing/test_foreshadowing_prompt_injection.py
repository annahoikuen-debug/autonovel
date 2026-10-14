import pytest
from unittest.mock import AsyncMock, MagicMock
from src.agents.prompt_composer import PromptComposer


@pytest.mark.asyncio
async def test_foreshadowing_context_passed_to_prompt_builder():
    """`foreshadowing_ctx` が渡された場合、PromptManager に正しく渡されること。"""
    mock_prompt_mgr = MagicMock()
    mock_prompt_mgr.build_final_writing_prompt = AsyncMock(return_value="GENERATED_PROMPT")

    agent = MagicMock()
    agent.prompt_manager = mock_prompt_mgr

    composer = PromptComposer(agent=agent)
    context = {
        "plot": {"detailed_blueprint": "Blueprint outline"},
        "foreshadowing_ctx": "【伏線FS-001: 謎のペンダント】",
    }

    result = await composer.compose_writing_prompt(
        book_id=1,
        ep_num=2,
        context=context,
    )

    assert result is not None
    # Verify build_final_writing_prompt received foreshadowing_context
    _, kwargs = mock_prompt_mgr.build_final_writing_prompt.call_args
    assert kwargs["foreshadowing_context"] == "【伏線FS-001: 謎のペンダント】"
