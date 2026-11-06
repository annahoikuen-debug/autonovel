"""次話プロンプトの投機生成が既定 OFF であることの回帰テスト（PLAN_W6 Step 4）。"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from src.services import semantic_cache as sc  # noqa: E402


def _mgr():
    vs = MagicMock()
    vs.get_collection = MagicMock()
    return sc.SemanticCacheManager(vector_store=vs, client=MagicMock())


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", raising=False)
    assert sc.is_draft_prefetch_enabled() is False


def test_flag_can_be_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", "true")
    assert sc.is_draft_prefetch_enabled() is True


def test_flag_accepts_truthy_spellings(monkeypatch):
    for raw in ("1", "TRUE", " yes ", "On"):
        monkeypatch.setenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", raw)
        assert sc.is_draft_prefetch_enabled() is True
    for raw in ("0", "false", "", "off"):
        monkeypatch.setenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", raw)
        assert sc.is_draft_prefetch_enabled() is False


@pytest.mark.asyncio
async def test_prefetch_next_is_noop_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", raising=False)
    mgr = _mgr()
    mgr._prefetch_embedding = AsyncMock()
    with patch("prompts.manager.PromptManager") as pm:
        await mgr.prefetch_next(1, 1, ["drafting"])
    pm.assert_not_called()
    assert mgr._prefetch_embedding.await_count == 0


@pytest.mark.asyncio
async def test_prefetch_next_spawns_no_background_task_by_default(monkeypatch):
    """既定 OFF のときは embedding 用のバックグラウンドタスクが1つも増えない。"""
    monkeypatch.delenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", raising=False)
    before = set(sc._BACKGROUND_TASKS)
    await _mgr().prefetch_next(1, 1, ["drafting", "polishing"])
    assert set(sc._BACKGROUND_TASKS) == before


@pytest.mark.asyncio
async def test_prefetch_by_pattern_still_reports_counts(monkeypatch):
    """Step 4 では `prefetch_by_pattern` の契約（戻り値）を変えない。"""
    monkeypatch.delenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", raising=False)
    result = await _mgr().prefetch_by_pattern(1, 1, 3, ["drafting"])
    assert result == {"total": 3, "succeeded": 3, "failed": 0}


@pytest.mark.asyncio
async def test_existing_public_api_intact():
    mgr = _mgr()
    for name in (
        "search",
        "add",
        "prefetch_next",
        "prefetch_by_pattern",
        "get_cache_warmth",
        "compute_similarity",
        "evict_if_needed",
    ):
        assert callable(getattr(mgr, name)), name


@pytest.mark.asyncio
async def test_enabled_path_still_works(monkeypatch):
    monkeypatch.setenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", "1")
    mgr = _mgr()
    mgr._prefetch_embedding = AsyncMock()
    with patch("prompts.manager.PromptManager") as pm:
        pm.return_value.build_drafting_prompt = AsyncMock(return_value="P")
        pm.return_value.build_polishing_prompt = AsyncMock(return_value="Q")
        await mgr.prefetch_next(1, 1, ["drafting", "polishing"])
    assert pm.return_value.build_drafting_prompt.await_count == 1
    assert pm.return_value.build_polishing_prompt.await_count == 1
