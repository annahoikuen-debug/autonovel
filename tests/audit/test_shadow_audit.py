"""M5-B: Shadow モードテスト。

- shadow_enabled=False → judge_mode="single", pairwise_verdict=None
- shadow_enabled=True, anchor_text=None → pairwise_verdict=None
- shadow_enabled=True, anchor_textあり → ペアワイズ呼ばれ、judge_mode="shadow"
- ペアワイズ失敗時も main_report は正常（シャドウは本番に影響なし）
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from src.agents.specialists.unified_auditor import UnifiedAuditor
from src.audit.judge_panel import JudgePanel, PairwiseVerdict
from src.audit.shadow_audit import (
    ShadowAuditResult,
    run_shadow_audit,
    run_shadow_pairwise_only,
)


class _FakeAuditor:
    """UnifiedAuditor をモック。"""

    def __init__(self, report: Any):
        self.report = report
        self.call_count = 0

    async def audit(
        self,
        text: str,
        character_profiles: str = "",
        plot_spec: str = "",
        db_session: Any = None,
        book_id: int = 0,
        ep_num: int = 0,
    ) -> Any:
        self.call_count += 1
        return self.report


class _FakePanel:
    """JudgePanel をモック。"""

    def __init__(self, verdict: PairwiseVerdict | None = None, fail: bool = False):
        self.verdict = verdict
        self.fail = fail
        self.call_count = 0

    async def pairwise(
        self,
        a: str,
        b: str,
        axis: str = "overall",
        *,
        provenance_family: str | None = None,
    ) -> PairwiseVerdict:
        self.call_count += 1
        if self.fail:
            raise RuntimeError("pairwise failure")
        return self.verdict


class _FakeReport:
    """UnifiedAuditReport をモック。"""

    def __init__(self, is_acceptable: bool = True, final_score: float = 80.0):
        self.is_acceptable = is_acceptable
        self.final_score = final_score


# ---- shadow_enabled=False ----


@pytest.mark.asyncio
async def test_shadow_disabled_single_mode(monkeypatch):
    """shadow_enabled=False → judge_mode="single", pairwise_verdict=None."""
    monkeypatch.setenv("ENABLE_PAIRWISE_SHADOW", "false")
    from src.audit import calibration_store

    calibration_store.clear_cache()

    auditor = _FakeAuditor(_FakeReport())
    panel = _FakePanel(verdict=PairwiseVerdict(winner="A", axis="overall"))

    result = await run_shadow_audit(
        auditor, panel, "テスト本文です。", book_id=1, ep_num=1
    )

    assert isinstance(result, ShadowAuditResult)
    assert result.shadow_enabled is False
    assert result.judge_mode == "single"
    assert result.pairwise_verdict is None
    assert result.main_report.is_acceptable is True
    assert auditor.call_count == 1
    assert panel.call_count == 0  # ペアワイズは呼ばれない


# ---- shadow_enabled=True, anchor_text=None ----


@pytest.mark.asyncio
async def test_shadow_enabled_no_anchor(monkeypatch):
    """shadow_enabled=True でも anchor_text None → pairwise_verdict=None."""
    monkeypatch.setenv("ENABLE_PAIRWISE_SHADOW", "true")
    from src.audit import calibration_store

    calibration_store.clear_cache()

    auditor = _FakeAuditor(_FakeReport())
    panel = _FakePanel(verdict=PairwiseVerdict(winner="A", axis="overall"))

    result = await run_shadow_audit(
        auditor, panel, "テスト本文です。", book_id=1, ep_num=1
    )

    assert result.shadow_enabled is True
    assert result.judge_mode == "shadow"
    assert result.pairwise_verdict is None  # anchor なし
    assert panel.call_count == 0


# ---- shadow_enabled=True, anchor_textあり ----


@pytest.mark.asyncio
async def test_shadow_enabled_with_anchor(monkeypatch):
    """shadow_enabled=True + anchorあり → ペアワイズ呼ばれ、judge_mode="shadow"。"""
    monkeypatch.setenv("ENABLE_PAIRWISE_SHADOW", "true")
    from src.audit import calibration_store

    calibration_store.clear_cache()

    auditor = _FakeAuditor(_FakeReport(is_acceptable=False, final_score=60.0))
    panel = _FakePanel(verdict=PairwiseVerdict(winner="B", axis="overall"))

    result = await run_shadow_audit(
        auditor,
        panel,
        "挑戦者本文です。",
        anchor_text="アンカー本文です。",
        book_id=2,
        ep_num=3,
    )

    assert result.shadow_enabled is True
    assert result.judge_mode == "shadow"
    assert result.pairwise_verdict is not None
    assert result.pairwise_verdict.winner == "B"
    assert result.main_report.is_acceptable is False  # 旧ゲートの結果は維持
    assert panel.call_count == 1


# ---- ペアワイズ失敗時も本番に影響なし ----


@pytest.mark.asyncio
async def test_shadow_pairwise_failure_no_impact(monkeypatch):
    """ペアワイズ失敗時も main_report は正常に返る。"""
    monkeypatch.setenv("ENABLE_PAIRWISE_SHADOW", "true")
    from src.audit import calibration_store

    calibration_store.clear_cache()

    auditor = _FakeAuditor(_FakeReport(is_acceptable=True, final_score=90.0))
    panel = _FakePanel(fail=True)

    result = await run_shadow_audit(
        auditor,
        panel,
        "テスト本文です。",
        anchor_text="アンカー本文です。",
    )

    assert result.main_report.is_acceptable is True
    assert result.main_report.final_score == 90.0
    assert result.pairwise_verdict is None  # 失敗したが本番には影響なし


# ---- run_shadow_pairwise_only ----


@pytest.mark.asyncio
async def test_run_shadow_pairwise_only_disabled(monkeypatch):
    """shadow 無効時は None。"""
    monkeypatch.setenv("ENABLE_PAIRWISE_SHADOW", "false")
    from src.audit import calibration_store

    calibration_store.clear_cache()

    panel = _FakePanel(verdict=PairwiseVerdict(winner="A", axis="overall"))
    result = await run_shadow_pairwise_only(panel, "A", "B")
    assert result is None


@pytest.mark.asyncio
async def test_run_shadow_pairwise_only_enabled(monkeypatch):
    """shadow 有効時はペアワイズ結果を返す。"""
    monkeypatch.setenv("ENABLE_PAIRWISE_SHADOW", "true")
    from src.audit import calibration_store

    calibration_store.clear_cache()

    panel = _FakePanel(verdict=PairwiseVerdict(winner="B", axis="overall"))
    result = await run_shadow_pairwise_only(panel, "A", "B")
    assert result is not None
    assert result.winner == "B"
