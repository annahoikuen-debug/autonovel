"""投機実行ゲートの純関数テスト（PLAN_W6 Step 11）。"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from src.backend.workflows.episode_writing_workflow import should_speculate  # noqa: E402


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_SPECULATIVE_PREFETCH", raising=False)
    assert should_speculate(100.0, True) is False


def test_flag_on_and_high_score(monkeypatch):
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    monkeypatch.setenv("PREFETCH_MIN_AUDIT_SCORE", "90")
    assert should_speculate(95.0, True) is True


def test_low_score_blocks(monkeypatch):
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    assert should_speculate(89.9, True) is False


def test_manual_mode_blocks(monkeypatch):
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    assert should_speculate(99.0, False) is False


def test_none_score_blocks(monkeypatch):
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    assert should_speculate(None, True) is False


def test_bad_threshold_falls_back(monkeypatch):
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    monkeypatch.setenv("PREFETCH_MIN_AUDIT_SCORE", "not-a-number")
    assert should_speculate(95.0, True) is True  # 既定 90 にフォールバック


def test_exact_threshold_is_allowed(monkeypatch):
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    monkeypatch.setenv("PREFETCH_MIN_AUDIT_SCORE", "90")
    assert should_speculate(90.0, True) is True


def test_non_numeric_score_blocks(monkeypatch):
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    assert should_speculate("unknown", True) is False


@pytest.mark.asyncio
async def test_trigger_prefetch_is_gated_by_default(monkeypatch):
    """既定では `_trigger_prefetch` が何もしない（投機タスクを作らない）こと。"""
    import asyncio
    from unittest.mock import MagicMock

    from src.backend.workflows.episode_writing_workflow import EpisodeWritingWorkflow

    monkeypatch.delenv("ENABLE_SPECULATIVE_PREFETCH", raising=False)
    monkeypatch.setenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", "1")
    wf = EpisodeWritingWorkflow.__new__(EpisodeWritingWorkflow)
    wf.vector_store = MagicMock()
    wf.llm_client = MagicMock()
    wf.reporter = MagicMock()
    wf.last_audit_score = 100.0
    wf.auto_mode = True
    await wf._trigger_prefetch(1, 1, wf.reporter)
    await asyncio.sleep(0.05)
    assert getattr(wf, "_semantic_cache", None) is None
    assert not getattr(wf, "_prefetch_tasks", set())
