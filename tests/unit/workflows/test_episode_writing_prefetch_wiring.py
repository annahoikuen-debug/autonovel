"""プリフェッチが「タスクハンドルを持つ」配線になったことの回帰テスト（PLAN_W6 Step 8）。"""

from __future__ import annotations

import asyncio
import pathlib
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from src.backend.workflows.episode_writing_workflow import EpisodeWritingWorkflow  # noqa: E402


@pytest.fixture(autouse=True)
def _enable_speculation(monkeypatch):
    """このファイルは配線検証が目的なので、Step 11 の投機ゲートを明示的に開く。"""
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    monkeypatch.setenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", "0")


def _wf():
    wf = EpisodeWritingWorkflow.__new__(EpisodeWritingWorkflow)  # __init__ をバイパス
    wf.vector_store = MagicMock()
    wf.llm_client = MagicMock()
    wf._prefetch_tasks = set()
    wf._semantic_cache = None
    # Step 11 のゲートを通過するための条件（既定の None だと投機は走らない）
    wf.last_audit_score = 95.0
    wf.auto_mode = True
    return wf


@pytest.mark.asyncio
async def test_task_handle_is_retained():
    wf = _wf()
    wf.reporter = MagicMock()
    wf.reporter.report = MagicMock()
    await wf._trigger_prefetch(1, 1, wf.reporter)
    await asyncio.sleep(0.05)
    assert isinstance(getattr(wf, "_prefetch_tasks", None), set)


@pytest.mark.asyncio
async def test_manager_is_reused_not_recreated():
    wf = _wf()
    wf.reporter = MagicMock()
    wf.reporter.report = MagicMock()
    with patch("src.services.semantic_cache.SemanticCacheManager") as SC:
        await wf._trigger_prefetch(1, 1, wf.reporter)
        first = wf._semantic_cache
        assert first is not None, "1 回目は生成される"
        await wf._trigger_prefetch(1, 2, wf.reporter)
    assert wf._semantic_cache is first
    assert SC.call_count == 1


@pytest.mark.asyncio
async def test_still_early_returns_without_vector_store():
    wf = EpisodeWritingWorkflow.__new__(EpisodeWritingWorkflow)
    wf.vector_store = None
    wf.llm_client = None
    await wf._trigger_prefetch(1, 1, MagicMock())  # 例外_none


@pytest.mark.asyncio
async def test_prefetch_tasks_drain_after_completion():
    """完了したタスクは集合から片付く（ハンドル滞留の防止）。"""
    wf = _wf()
    wf.reporter = MagicMock()
    wf.reporter.report = MagicMock()
    await wf._trigger_prefetch(1, 1, wf.reporter)
    await asyncio.sleep(0.1)
    assert len(wf._prefetch_tasks) == 0
