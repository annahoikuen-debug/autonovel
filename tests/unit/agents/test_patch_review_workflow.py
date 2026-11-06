"""Patch Review Workflow E2E Tests"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.audit_agent import AuditAgent
from src.agents.orchestrator import AgentContext, AgentName
from src.engine.conflict_report_service import ConflictReportService
from src.services.learning_data_service import LearningDataService


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.misc = MagicMock()
    repo.audit = MagicMock()
    return repo


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def audit_agent(mock_repo, mock_llm, monkeypatch):
    # NOTE: 本テスト群は legacy core (5監査: _fast_screener 等) の前提でモックを
    # 設定するため、AuditAgent 生成前に ENABLE_AUDIT_LEGACY_CORE を有効化する。
    # (デフォルトは UnifiedAuditor のみで _plot_monitor 等は None)
    monkeypatch.setenv("ENABLE_AUDIT_LEGACY_CORE", "true")
    agent = AuditAgent(repo=mock_repo, llm=mock_llm)
    # UnifiedAuditor を無効化 (llm が MagicMock のため遅延生成されると
    # await できない例外で run() が即座に落ちる。本テスト群は第6観点を対象外とする)
    agent._unified_auditor = None
    agent._unified_auditor_resolved = True
    return agent


@pytest.mark.asyncio
async def test_audit_agent_creates_patch_review_on_failure(audit_agent, mock_repo):
    """監査失敗時に PatchReview が作成されることを確認"""
    # モック設定
    mock_repo.misc.create_patch_review = AsyncMock(return_value=42)
    mock_repo.audit.create_audit_issue = AsyncMock(return_value=1)

    # 監査コンポーネントをモック
    audit_agent._fast_screener.screen_plot = AsyncMock(return_value=(False, "Plot invalid"))
    audit_agent._logical_auditor.audit_logical_consistency = AsyncMock(return_value=(False, "Logical issue", 0.0))
    audit_agent._deai_auditor.audit = AsyncMock(return_value=(True, "OK"))
    audit_agent._ability_checker.audit_ability_consistency = AsyncMock(return_value=(True, "OK", ""))
    audit_agent._plot_monitor.extract_keywords = AsyncMock(return_value=[])
    audit_agent._plot_monitor.check_integrity = AsyncMock(return_value=(True, 1.0, None))

    ctx = AgentContext(
        book_id=1,
        branch_id=1,
        ep_num=1,
        artifacts={
            "writing_context": {"plot": {"detailed_blueprint": "test plot"}},
            "drafted_text": "test content",
        },
    )

    result = await audit_agent.run(ctx)

    # 実装は requires_user_review / patch_review_id を artifacts に入れる
    assert result.artifacts["requires_user_review"] is True
    assert result.artifacts["patch_review_id"] == 42
    # 監査失敗時は全文再執筆 (WRITING へ backtrack) が走る
    assert result.next_agent == AgentName.WRITING
    assert result.should_retry is True
    assert result.is_backtrack is True
    mock_repo.misc.create_patch_review.assert_called_once()
    mock_repo.audit.create_audit_issue.assert_called()


@pytest.mark.asyncio
async def test_audit_agent_passes_when_all_audits_ok(audit_agent, mock_repo):
    """全監査合格時は次エージェントへ進むことを確認"""
    audit_agent._fast_screener.screen_plot = AsyncMock(return_value=(True, "OK"))
    audit_agent._logical_auditor.audit_logical_consistency = AsyncMock(return_value=(True, "OK", 1.0))
    audit_agent._deai_auditor.audit = AsyncMock(return_value=(True, "OK"))
    audit_agent._ability_checker.audit_ability_consistency = AsyncMock(return_value=(True, "OK", ""))
    audit_agent._plot_monitor.extract_keywords = AsyncMock(return_value=[])
    audit_agent._plot_monitor.check_integrity = AsyncMock(return_value=(True, 1.0, None))

    ctx = AgentContext(
        book_id=1,
        branch_id=1,
        ep_num=1,
        artifacts={
            "writing_context": {"plot": {"detailed_blueprint": "test plot"}},
            "drafted_text": "test content",
        },
    )

    result = await audit_agent.run(ctx)

    assert result.next_agent == AgentName.ILLUSTRATION
    # 現実装の audit_report は {unified, final_score, audit_ids} 形式
    assert result.artifacts["audit_report"]["unified"] == "passed"
    assert result.artifacts["audit_status"] == "passed"
    assert not result.artifacts.get("requires_user_review")


@pytest.mark.asyncio
async def test_conflict_report_generation():
    """矛盾レポート生成のテスト"""
    service = ConflictReportService()

    failed_audits = [
        {"type": "logical_consistency", "feedback": "Character A cannot be in two places", "severity": "high"},
        {"type": "causal_integrity", "feedback": "Effect precedes cause", "severity": "critical"},
    ]

    report = service.generate_conflict_report(
        book_id=1,
        ep_num=5,
        failed_audits=failed_audits,
    )

    assert report.book_id == 1
    assert report.ep_num == 5
    assert report.total_count == 2
    assert report.critical_count == 1
    assert report.high_count == 1
    assert len(report.conflicts) == 2


@pytest.mark.asyncio
async def test_learning_data_service_negative_sample(mock_repo):
    """ネガティブサンプル記録のテスト"""
    mock_chroma = MagicMock()
    mock_collection = MagicMock()
    mock_chroma.get_or_create_collection.return_value = mock_collection

    service = LearningDataService(repo=mock_repo, chroma_client=mock_chroma)

    mock_repo.misc.get_patch_review = AsyncMock(return_value={
        "id": 1,
        "audit_issue_ids": [1, 2],
        "learning_metadata": {"negative_sample_candidates": ["logical_consistency", "causal_integrity"]},
    })
    mock_repo.session.execute = AsyncMock()

    count = await service.record_negative_sample(
        patch_review_id=1,
        resolution="rejected",
        reviewer_id="user1",
        comment="This is not actually a contradiction",
    )

    assert count == 2
    mock_collection.add.assert_called()


@pytest.mark.asyncio
async def test_audit_agent_learning_adjustment(audit_agent, mock_repo):
    """学習データによる監査調整のテスト"""
    # 学習サービスのモック
    audit_agent._learning_service.should_skip_audit_type = AsyncMock(return_value=(True, -0.3))

    audit_agent._fast_screener.screen_plot = AsyncMock(return_value=(True, "OK"))
    audit_agent._logical_auditor.audit_logical_consistency = AsyncMock(return_value=(False, "Logical issue", 0.0))
    audit_agent._deai_auditor.audit = AsyncMock(return_value=(True, "OK"))
    audit_agent._ability_checker.audit_ability_consistency = AsyncMock(return_value=(True, "OK", ""))
    audit_agent._plot_monitor.extract_keywords = AsyncMock(return_value=[])
    audit_agent._plot_monitor.check_integrity = AsyncMock(return_value=(True, 1.0, None))

    mock_repo.misc.create_patch_review = AsyncMock(return_value=42)
    mock_repo.audit.create_audit_issue = AsyncMock(return_value=1)

    ctx = AgentContext(
        book_id=1,
        branch_id=1,
        ep_num=1,
        artifacts={
            "writing_context": {"plot": {"detailed_blueprint": "test plot"}},
            "drafted_text": "test content",
        },
    )

    result = await audit_agent.run(ctx)

    # 学習調整された監査が含まれることを確認
    assert "learning_adjusted_audits" in result.artifacts
    assert "logical_consistency" in result.artifacts["learning_adjusted_audits"]
