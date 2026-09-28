"""Coverage tests for src/backend/engine_facade.py and src/backend/engine_plot.py."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.backend.engine_config import EngineConfig
from src.backend.engine_facade import EngineFacade
from src.backend.engine_utils import AdaptiveCooldown


# --------------------------------------------------------------------------
# engine_facade
# --------------------------------------------------------------------------

@pytest.fixture
def facade():
    engine = MagicMock()
    engine.generate_json = "unused"
    return EngineFacade(EngineConfig.create("key"), engine)


def test_facade_config_accessors(facade):
    assert facade.api_key == "key"
    assert isinstance(facade.cooldown, AdaptiveCooldown)
    assert facade.engine_impl is facade._engine


@pytest.mark.parametrize(
    "attr",
    [
        "repo", "llm", "pm", "ctx_mgr", "formatter", "validator", "auditor",
        "narrative", "critique", "marketing", "bible_agent", "plot_agent",
        "style_rag", "db", "planner", "writer", "plot_service",
    ],
)
def test_facade_property_delegation(facade, attr):
    sentinel = MagicMock()
    setattr(facade._engine, attr, sentinel)
    assert getattr(facade, attr) is sentinel


def test_facade_logic_validator_and_generate_json(facade):
    sentinel = MagicMock()
    facade._engine.validator = sentinel
    assert facade.logic_validator is sentinel

    facade._engine.llm.generate_json = "json-fn"
    assert facade.generate_json == "json-fn"


def test_facade_dispose(facade):
    facade._engine.db.engine = MagicMock()
    facade.dispose()
    facade._engine.db.engine.dispose.assert_called_once()


def test_facade_dispose_without_engine_attr(facade):
    del facade._engine.db.engine
    facade.dispose()  # must not raise


async def test_facade_method_delegation(facade):
    facade._engine.sync_bible = AsyncMock(return_value="bible")
    assert await facade.sync_bible(1, reporter="rep") == "bible"

    facade._engine.resolve_bible_setting = AsyncMock(return_value=None)
    assert await facade.resolve_bible_setting(2, "active") is None

    facade._engine.determine_target_tension = AsyncMock(return_value=0.75)
    assert await facade.determine_target_tension(1, 2, "fantasy", "type") == 0.75

    facade._engine.validate_tension_deviation = AsyncMock(return_value=(True, 0.1))
    assert await facade.validate_tension_deviation(1, 0.5, 2) == (True, 0.1)


# --------------------------------------------------------------------------
# engine_plot
# --------------------------------------------------------------------------

def _plot(**kwargs):
    from src.models.db import PlotDbModel

    return PlotDbModel(book_id=1, ep_num=1, **kwargs)


def test_build_default_hook():
    from src.backend.engine_plot import _build_default_hook

    hook = _build_default_hook()
    assert hook.hook_name == "catharsis"
    assert hook.target_tension_peak == 85


def test_resolve_emotional_hook_variants():
    from src.backend.engine_plot import resolve_emotional_hook

    assert resolve_emotional_hook(None) is None
    assert resolve_emotional_hook(_plot()) is None

    hook_json = json.dumps({"hook_name": "triumph", "one_line_intent": "復讐", "target_tension_peak": 70})
    hook = resolve_emotional_hook(_plot(emotional_hook_json=hook_json))
    assert hook is not None and hook.hook_name == "triumph"

    assert resolve_emotional_hook(_plot(emotional_hook_json="{bad json")) is None
    assert resolve_emotional_hook(_plot(emotional_hook_json="[1, 2]")) is None


async def test_get_emotional_hook_prefers_plot():
    from src.backend.engine_plot import get_emotional_hook_for_plot

    hook_json = json.dumps({"hook_name": "triumph", "one_line_intent": "x", "target_tension_peak": 50})
    repo = MagicMock()
    repo.get_plot = AsyncMock(return_value=None)
    hook = await get_emotional_hook_for_plot(_plot(emotional_hook_json=hook_json), repo, 1, 1)
    assert hook.hook_name == "triumph"
    repo.get_plot.assert_not_awaited()


async def test_get_emotional_hook_loads_from_repo():
    from src.backend.engine_plot import get_emotional_hook_for_plot

    hook_json = json.dumps({"hook_name": "despair_to_hope", "one_line_intent": "x", "target_tension_peak": 50})
    repo = MagicMock()
    repo.get_plot = AsyncMock(return_value=_plot(emotional_hook_json=hook_json))
    hook = await get_emotional_hook_for_plot(None, repo, 1, 1)
    assert hook.hook_name == "despair_to_hope"


async def test_get_emotional_hook_repo_error_falls_back_to_default():
    from src.backend.engine_plot import get_emotional_hook_for_plot

    repo = MagicMock()
    repo.get_plot = AsyncMock(side_effect=RuntimeError("db down"))
    hook = await get_emotional_hook_for_plot(None, repo, 1, 1)
    assert hook.hook_name == "catharsis"

    hook = await get_emotional_hook_for_plot(None, None, 1, 1)
    assert hook.hook_name == "catharsis"


def test_ensure_emotional_hook_set():
    from src.backend import engine_plot

    with pytest.raises(RuntimeError, match="emotional_hook が未設定"):
        engine_plot.ensure_emotional_hook_set(_plot())

    hook_json = json.dumps({"hook_name": "catharsis", "one_line_intent": "x", "target_tension_peak": 80})
    engine_plot.ensure_emotional_hook_set(_plot(emotional_hook_json=hook_json))

    monkey = engine_plot.ENFORCE_ENTERTAINMENT_FIRST
    try:
        engine_plot.ENFORCE_ENTERTAINMENT_FIRST = False
        engine_plot.ensure_emotional_hook_set(_plot())
    finally:
        engine_plot.ENFORCE_ENTERTAINMENT_FIRST = monkey


def test_parse_sharp_edges_variants():
    from src.backend.engine_plot import _parse_sharp_edges

    assert _parse_sharp_edges(None) == []
    assert _parse_sharp_edges("") == []
    assert _parse_sharp_edges("{not json") == []
    assert _parse_sharp_edges(json.dumps({"a": 1})) == []

    good = {
        "edge_type": "protagonist_flaw",
        "description": "短気",
        "key_phrase": "|TYPED_PHRASE>",
    }
    edges = _parse_sharp_edges(json.dumps([good]))
    assert len(edges) == 1
    assert edges[0].edge_type == "protagonist_flaw"
    assert edges[0].preserve_on_quality_polish is True

    # unknown edge type / non dict entries are skipped
    payload = [{"edge_type": "unknown"}, "text", 5, {**good, "preserve_on_quality_polish": False}]
    edges = _parse_sharp_edges(json.dumps(payload))
    assert len(edges) == 1
    assert edges[0].preserve_on_quality_polish is False

    # over-long key_phrase is truncated
    long_payload = [{**good, "key_phrase": "x" * 40}]
    edges = _parse_sharp_edges(json.dumps(long_payload))
    assert len(edges[0].key_phrase) == 20


def test_parse_sharp_edges_validation_error_skips(monkeypatch):
    from pydantic import ValidationError

    from src.backend import engine_plot

    def _boom(**kwargs):
        raise ValidationError.from_exception_data("SharpEdgeSpec", [])

    monkeypatch.setattr(engine_plot, "SharpEdgeSpec", _boom)
    payload = [{"edge_type": "protagonist_flaw", "description": "d", "key_phrase": "k"}]
    assert engine_plot._parse_sharp_edges(json.dumps(payload)) == []


async def test_propose_sharp_edges():
    from src.backend.engine_plot import propose_sharp_edges

    assert await propose_sharp_edges(None, "summary") == []

    pm = MagicMock()
    pm.build_sharp_edge_proposal_prompt = AsyncMock(return_value="prompt")
    assert await propose_sharp_edges(pm, "summary") == []

    pm2 = MagicMock()
    pm2.build_sharp_edge_proposal_prompt = AsyncMock(side_effect=RuntimeError("no llm"))
    assert await propose_sharp_edges(pm2, "summary") == []


def test_resolve_sharp_edges():
    from src.backend.engine_plot import resolve_sharp_edges

    assert resolve_sharp_edges(None) == []
    assert resolve_sharp_edges(_plot()) == []
    payload = json.dumps([{"edge_type": "sharp_conflict", "description": "d", "key_phrase": "k"}])
    edges = resolve_sharp_edges(_plot(sharp_edges_json=payload))
    assert len(edges) == 1


async def test_enforce_entertainment_gate(monkeypatch):
    from src.backend import engine_plot

    class _Result:
        interest_score = 90

    async def fake_loop(**kwargs):
        return _Result()

    monkeypatch.setattr(
        "src.backend.entertainment_loop.run_entertainment_first_loop", fake_loop
    )
    result = await engine_plot.enforce_entertainment_gate(MagicMock(), "plot", "chars")
    assert result.interest_score == 90

    class _Low:
        interest_score = 10

    async def fake_low(**kwargs):
        return _Low()

    monkeypatch.setattr(
        "src.backend.entertainment_loop.run_entertainment_first_loop", fake_low
    )
    with pytest.raises(RuntimeError, match="面白さ検証不合格"):
        await engine_plot.enforce_entertainment_gate(MagicMock(), "plot", "chars")
