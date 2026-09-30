"""関連度注入が既定OFFで、ONにしても契約鉤子が消えないことの回帰テスト（PLAN_W5 Step 10）。"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.agents.prompt_composer import PromptComposer  # noqa: E402


def _composer() -> PromptComposer:
    agent = MagicMock()
    agent.prompt_manager = MagicMock()
    agent.prompt_manager.build_final_writing_prompt = AsyncMock(return_value="PROMPT")
    return PromptComposer(agent)


ROWS = [
    {"id": 1, "title": "古代の魔導書", "description": "巻物", "planted_episode": 2},
    {"id": 2, "title": "幼馴染の約束", "description": "町の言葉", "planted_episode": 3},
]


@pytest.mark.asyncio
async def test_default_off_passes_everything(monkeypatch):
    monkeypatch.setenv("FORESHADOW_RELEVANCE_INJECTION", "0")
    out = await _composer()._load_unresolved_foreshadowings(
        book_id=1, ep_num=1, context={}, rows=ROWS
    )
    assert [c["id"] for c in out] == [1, 2]
    assert all("relevance" not in c for c in out)


@pytest.mark.asyncio
async def test_on_flag_limits_to_top_k(monkeypatch):
    monkeypatch.setenv("FORESHADOW_RELEVANCE_INJECTION", "1")
    monkeypatch.setenv("FORESHADOW_RELEVANCE_TOP_K", "1")
    out = await _composer()._load_unresolved_foreshadowings(
        book_id=1,
        ep_num=1,
        context={"scene_summary": "魔導書を読み解こうとする"},
        rows=ROWS,
    )
    assert len(out) == 1
    assert out[0]["id"] == 1
    assert "relevance" in out[0]


@pytest.mark.asyncio
async def test_on_flag_never_returns_empty(monkeypatch):
    monkeypatch.setenv("FORESHADOW_RELEVANCE_INJECTION", "1")
    monkeypatch.setenv("FORESHADOW_RELEVANCE_TOP_K", "1")
    out = await _composer()._load_unresolved_foreshadowings(
        book_id=1,
        ep_num=1,
        context={},
        rows=[{"id": 9, "title": "無関係", "description": "無関係", "planted_episode": 1}],
    )
    assert len(out) >= 1


@pytest.mark.asyncio
async def test_on_flag_with_no_rows_returns_empty(monkeypatch):
    monkeypatch.setenv("FORESHADOW_RELEVANCE_INJECTION", "1")
    out = await _composer()._load_unresolved_foreshadowings(
        book_id=1, ep_num=1, context={}, rows=[]
    )
    assert out == []


@pytest.mark.asyncio
async def test_context_provided_rows_win_over_rows_argument(monkeypatch):
    """既存の `context["unresolved_foreshadowings"]` 経路を壊さない。"""
    monkeypatch.setenv("FORESHADOW_RELEVANCE_INJECTION", "0")
    out = await _composer()._load_unresolved_foreshadowings(
        book_id=1,
        ep_num=1,
        context={"unresolved_foreshadowings": [{"id": 42, "title": "x"}]},
    )
    assert [c["id"] for c in out] == [42]


@pytest.mark.asyncio
async def test_contract_foreshadowings_are_not_touched():
    """契約鉤子は関連度で削らない（`_format_contract_foreshadowings` は無変更）。"""
    text = PromptComposer._format_contract_foreshadowings(
        [{"id": 7, "title": "約束", "description": "d", "planted_episode": 1, "target_episode": 5}]
    )
    assert "伏線ID: 7" in text
