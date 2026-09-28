"""src/agents/early_entertainment_checker.py の単体テスト."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.early_entertainment_checker import EarlyEntertainmentChecker


async def test_check_without_prompt_manager():
    checker = EarlyEntertainmentChecker(llm=MagicMock(), prompt_manager=None)
    res = await checker.check("plot", "opening")
    assert res.interest_score == 0
    assert res.physiological_reaction == "無反応"
    assert res.would_continue_reading is False
    assert res.feedback == "prompt_managerが未設定"


async def test_check_success():
    llm = MagicMock()
    llm.generate_json = AsyncMock(
        return_value={
            "metadata": {
                "interest_score": 82.7,
                "physiological_reaction": "鳥肌",
                "would_continue_reading": True,
                "feedback": "x" * 500,
            }
        }
    )
    pm = MagicMock()
    pm.build_early_entertainment_check_prompt = AsyncMock(return_value="prompt")
    checker = EarlyEntertainmentChecker(llm=llm, prompt_manager=pm)
    res = await checker.check("plot", "opening")
    assert res.interest_score == 82
    assert res.physiological_reaction == "鳥肌"
    assert res.would_continue_reading is True
    assert len(res.feedback) == 300


@pytest.mark.parametrize("score", [-5, 150, "abc", None])
async def test_check_invalid_score_is_zeroed(score):
    llm = MagicMock()
    llm.generate_json = AsyncMock(return_value={"metadata": {"interest_score": score}})
    pm = MagicMock()
    pm.build_early_entertainment_check_prompt = AsyncMock(return_value="p")
    checker = EarlyEntertainmentChecker(llm=llm, prompt_manager=pm)
    res = await checker.check("plot", "opening")
    assert res.interest_score == 0
    assert res.physiological_reaction == "無反応"
    assert res.feedback == ""


async def test_check_llm_failure_fallback():
    llm = MagicMock()
    llm.generate_json = AsyncMock(side_effect=RuntimeError("boom"))
    pm = MagicMock()
    pm.build_early_entertainment_check_prompt = AsyncMock(return_value="p")
    checker = EarlyEntertainmentChecker(llm=llm, prompt_manager=pm)
    res = await checker.check("plot", "opening")
    assert res.interest_score == 0
    assert res.feedback == "検証失敗"
