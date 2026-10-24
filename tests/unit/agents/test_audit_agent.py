"""Tests for src/agents/audit_agent.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.audit_agent import (
    AuditAgent,
    AuditCriterion,
    AUDIT_GATE_PASS_SCORE,
    AUDIT_GATE_SEVERITY_WEIGHTS,
    CORE_AUDIT_CRITERIA,
    UNIFIED_AUDIT_CRITERION,
    evaluate_gate,
    is_score_gate_enabled,
    get_gate_threshold,
)
from src.agents.orchestrator import AgentContext, AgentName


# ---------------------------------------------------------------------------
# Helper fixtures and constants
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_repo():
    """Mock repository."""
    repo = MagicMock()
    repo.misc = MagicMock()
    repo.misc.create_patch_review = AsyncMock(return_value=123)
    repo.audit = MagicMock()
    repo.audit.create_audit_issue = AsyncMock(return_value=456)
    return repo


@pytest.fixture
def mock_llm():
    """Mock LLM."""
    llm = MagicMock()
    # Properly mock the LLM for both direct calls and generate_json
    llm.generate_json = AsyncMock(
        return_value={
            "hook_score": 85.0,
            "emotional_score": 90.0,
            "character_consistency": 80.0,
            "overall_score": 85.0,
            "critique": "良好なストーリーです。",
            "actionable_patch": None,
        }
    )
    llm.generate = AsyncMock(
        return_value="""{
        "hook_score": 85.0,
        "emotional_score": 90.0,
        "character_consistency": 80.0,
        "overall_score": 85.0,
        "critique": "良好なストーリーです。",
        "actionable_patch": null
    }"""
    )
    llm.generate_text = AsyncMock(
        return_value="""{
        "hook_score": 85.0,
        "emotional_score": 90.0,
        "character_consistency": 80.0,
        "overall_score": 85.0,
        "critique": "良好なストーリーです。",
        "actionable_patch": null
    }"""
    )
    llm.return_value = {"metadata": {"is_valid": True, "feedback": "OK"}}
    return llm


@pytest.fixture
def mock_prompt_manager():
    """Mock prompt manager."""
    pm = MagicMock()
    pm.build_fast_plot_screen_prompt = MagicMock(return_value="fast prompt")
    pm.build_ability_audit_prompt = MagicMock(return_value="ability prompt")
    pm.build_critic_feedback_prompt = MagicMock(return_value="critic prompt")
    return pm


@pytest.fixture
def mock_edge_preserver():
    """Mock edge preserver."""
    preserver = MagicMock()
    preserver.check_edges_preserved = AsyncMock(return_value=([], 0.0))
    return preserver


@pytest.fixture
def audit_agent(mock_repo, mock_llm, mock_prompt_manager, mock_edge_preserver):
    """AuditAgent instance with mocked dependencies."""
    return AuditAgent(
        repo=mock_repo,
        llm=mock_llm,
        prompt_manager=mock_prompt_manager,
        edge_preserver=mock_edge_preserver,
    )


@pytest.fixture
def sample_writing_context():
    """Sample writing context."""
    return {
        "plot": {"detailed_blueprint": "青年の主人公が村を出て冒険に旅立つ。"},
        "world_settings": '{"magic_system": "元素魔法"}',
        "characters_json": '[{"name": "主人公", "role": "主人公"}]',
        "sharp_edges": [],
        "emotional_hook": None,
        "prev_ctx": "",
    }


@pytest.fixture
def sample_drafted_text():
    """Sample drafted text."""
    return "主人公は村を出て冒険の旅に出た。"


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


def test_audit_agent_init_defaults(mock_repo, mock_llm, mock_prompt_manager, mock_edge_preserver):
    """AuditAgent initialization sets internal components."""
    agent = AuditAgent(
        repo=mock_repo,
        llm=mock_llm,
        prompt_manager=mock_prompt_manager,
        edge_preserver=mock_edge_preserver,
    )
    assert agent.repo is mock_repo
    assert agent.llm is mock_llm
    assert agent.prompt_manager is mock_prompt_manager
    assert agent._logical_auditor is not None
    assert agent._deai_auditor is not None
    assert agent._fast_screener is not None
    assert agent._ability_checker is not None
    assert agent._plot_monitor is not None
    assert agent._learning_service is not None
    assert agent._audit_llm is mock_llm  # defaults to llm
    assert agent._unified_auditor is None  # not provided
    assert agent._unified_auditor_resolved is False
    assert agent.last_audit_latency_seconds is None
    assert agent.last_audit_durations == {}
    assert agent.last_gate_evaluation is None
    assert agent.last_unified_report is None
    assert agent._emitted_events == []


def test_audit_agent_init_with_unified_auditor(mock_repo, mock_llm, mock_prompt_manager, mock_edge_preserver):
    """AuditAgent with pre-provided unified auditor."""
    unified = MagicMock()
    agent = AuditAgent(
        repo=mock_repo,
        llm=mock_llm,
        prompt_manager=mock_prompt_manager,
        edge_preserver=mock_edge_preserver,
        unified_auditor=unified,
    )
    assert agent._unified_auditor is unified
    assert agent._unified_auditor_resolved is True


# ---------------------------------------------------------------------------
# Environment flag tests
# ---------------------------------------------------------------------------


def test_is_score_gate_enabled_default(monkeypatch):
    """is_score_gate_enabled respects environment and default."""
    monkeypatch.delenv("ENABLE_AUDIT_SCORE_GATE", raising=False)
    assert is_score_gate_enabled() is True  # default ON

    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "false")
    assert is_score_gate_enabled() is False

    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "true")
    assert is_score_gate_enabled() is True


def test_get_gate_threshold_default(monkeypatch):
    """get_gate_threshold respects environment and default."""
    monkeypatch.delenv("AUDIT_GATE_THRESHOLD", raising=False)
    assert get_gate_threshold() == 70.0  # default

    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "80.5")
    assert get_gate_threshold() == 80.5

    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "invalid")
    assert get_gate_threshold() == 70.0  # fallback on error


# ---------------------------------------------------------------------------
# Core audit running tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_core_audits_blueprint_missing(audit_agent, sample_writing_context, sample_drafted_text):
    """_run_core_audits removes fast_screen when blueprint missing."""
    ctx = dict(sample_writing_context)
    ctx["plot"]["detailed_blueprint"] = ""  # empty blueprint
    plan = await audit_agent._run_core_audits(ctx, sample_drafted_text, book_id=1, ep_num=1)
    audit_ids = [c.audit_id for c, _ in plan]
    assert "fast_screen" not in audit_ids
    assert set(audit_ids) == {"logical_consistency", "deai", "ability_consistency", "causal_integrity"}


@pytest.mark.asyncio
async def test_run_core_audits_factories(audit_agent, sample_writing_context, sample_drafted_text):
    """_run_core_audits returns correct factory functions."""
    plan = await audit_agent._run_core_audits(sample_writing_context, sample_drafted_text, book_id=1, ep_num=1)
    assert len(plan) == len(CORE_AUDIT_CRITERIA)
    # Each item is (criterion, factory_callable)
    for criterion, factory in plan:
        assert criterion in CORE_AUDIT_CRITERIA
        assert callable(factory)


# ---------------------------------------------------------------------------
# Outcome conversion tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_core_to_outcome_passed(audit_agent):
    """_core_to_outcome builds passed outcome."""
    criterion = AuditCriterion(audit_id="test", label="Test", severity="high", learning_key="test")
    raw = (True, "All good")
    outcome = await audit_agent._core_to_outcome(criterion, raw)
    assert outcome["passed"] is True
    assert outcome["score"] == AUDIT_GATE_PASS_SCORE
    assert outcome["feedback"] == "All good"
    assert outcome["severity"] == "high"
    assert outcome["effective_severity"] is None
    assert outcome["learning_adjusted"] is False
    assert outcome["confidence_adjustment"] == 0.0


@pytest.mark.asyncio
async def test_core_to_outcome_failed_no_learning(audit_agent):
    """_core_to_outcome builds failed outcome without learning adjustment."""
    criterion = AuditCriterion(audit_id="test", label="Test", severity="high", learning_key="test")
    raw = (False, "Failed", "extra")
    with patch.object(audit_agent, "_check_learning_adjustment", AsyncMock(return_value=(False, 0.0))):
        outcome = await audit_agent._core_to_outcome(criterion, raw)
    assert outcome["passed"] is False
    assert outcome["feedback"] == "Failed"
    assert outcome["severity"] == "high"
    assert outcome["effective_severity"] == "high"  # not downgraded
    assert outcome["learning_adjusted"] is False
    assert outcome["confidence_adjustment"] == 0.0
    # Score: high severity -> penalty 30.0, no confidence adjustment
    assert outcome["score"] == 30.0
    assert outcome["weight"] == AUDIT_GATE_SEVERITY_WEIGHTS["high"]  # 1.5
    assert outcome["detail"]["raw"] == "extra"


@pytest.mark.asyncio
async def test_core_to_outcome_failed_with_learning(audit_agent):
    """_core_to_outcome builds failed outcome with learning adjustment."""
    criterion = AuditCriterion(audit_id="test", label="Test", severity="high", learning_key="test")
    raw = (False, "Failed")
    with patch.object(audit_agent, "_check_learning_adjustment", AsyncMock(return_value=(True, 0.5))):
        outcome = await audit_agent._core_to_outcome(criterion, raw)
    assert outcome["learning_adjusted"] is True
    assert outcome["effective_severity"] == "medium"  # downgraded from high
    assert outcome["confidence_adjustment"] == 0.5
    # Score: medium severity -> penalty 60.0, confidence 0.5 * 10.0 = 5.0
    assert outcome["score"] == 65.0  # 60 + 5
    assert outcome["weight"] == AUDIT_GATE_SEVERITY_WEIGHTS["medium"]  # 1.0


def test_unified_to_outcome_degraded(audit_agent):
    """_unified_to_outcome handles degraded tuple."""
    criterion = UNIFIED_AUDIT_CRITERION
    raw = ("degraded", "LLM missing")
    outcome = audit_agent._unified_to_outcome(criterion, raw)
    assert outcome["passed"] is False
    assert outcome["feedback"] == "LLM missing"
    assert outcome["error"] == "LLM missing"
    assert outcome["detail"]["degraded"] is True
    assert outcome["blocking"] is False  # unified auditor not blocking by default


def test_unified_to_outcome_accepted(audit_agent):
    """_unified_to_outcome handles accepted UnifiedAuditor report."""
    criterion = UNIFIED_AUDIT_CRITERION
    # Mock report object
    report = MagicMock()
    report.is_acceptable = True
    report.final_score = 85.0
    report.qualitative = MagicMock()
    report.qualitative.critique = "Good flow"
    report.conflicts = []
    outcome = audit_agent._unified_to_outcome(criterion, report)
    assert outcome["passed"] is True
    assert outcome["feedback"] == "Good flow"
    assert outcome["score"] == AUDIT_GATE_PASS_SCORE
    assert outcome["detail"]["final_score"] == 85.0
    assert outcome["blocking"] is False


def test_unified_to_outcome_rejected(audit_agent):
    """_unified_to_outcome handles rejected UnifiedAuditor report."""
    criterion = UNIFIED_AUDIT_CRITERION
    report = MagicMock()
    report.is_acceptable = False
    report.final_score = 45.0
    report.qualitative = MagicMock()
    report.qualitative.critique = "Weak plot"
    report.conflicts = []
    outcome = audit_agent._unified_to_outcome(criterion, report)
    assert outcome["passed"] is False
    assert outcome["feedback"] == "Weak plot"
    assert outcome["effective_severity"] == criterion.severity  # "medium"
    assert outcome["detail"]["final_score"] == 45.0


# ---------------------------------------------------------------------------
# Full audit phase tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_audit_phase_parallel_success(
    audit_agent,
    sample_writing_context,
    sample_drafted_text,
    mock_repo,
    mock_llm,
    mock_prompt_manager,
    mock_edge_preserver,
):
    """run_audit_phase runs audits in parallel and returns outcomes."""
    # Mock all internal auditors to return success
    with (
        patch.object(audit_agent._fast_screener, "screen_plot", AsyncMock(return_value=(True, "OK"))),
        patch.object(
            audit_agent._logical_auditor, "audit_logical_consistency", AsyncMock(return_value=(True, "OK", 0.9))
        ),
        patch.object(audit_agent._deai_auditor, "audit", AsyncMock(return_value=(True, "OK"))),
        patch.object(
            audit_agent._ability_checker,
            "audit_ability_consistency",
            AsyncMock(return_value=(True, "OK", "suggestion")),
        ),
        patch.object(audit_agent._plot_monitor, "extract_keywords", AsyncMock(return_value=["主人公", "村"])),
        patch.object(audit_agent._plot_monitor, "check_integrity", AsyncMock(return_value=(True, 0.9, MagicMock()))),
        patch.object(audit_agent, "_resolve_unified_auditor", return_value=None),
    ):
        outcomes, latency = await audit_agent.run_audit_phase(
            sample_writing_context, sample_drafted_text, book_id=42, ep_num=7, parallel=True
        )

    assert isinstance(outcomes, list)
    assert len(outcomes) == 6  # 5 core + 1 unified (degraded because no unified_auditor provided)
    assert latency >= 0
    # Check that all core audits passed
    core_outcomes = [o for o in outcomes if o["audit_id"] in [c.audit_id for c in CORE_AUDIT_CRITERIA]]
    assert all(o["passed"] for o in core_outcomes)
    # Unified should be degraded (no LLM provided for unified auditor)
    unified_outcome = [o for o in outcomes if o["audit_id"] == "unified_qualitative"][0]
    assert unified_outcome["passed"] is False
    assert unified_outcome["feedback"] == "UnifiedAuditor に LLM が設定されていません"


@pytest.mark.asyncio
async def test_run_audit_phase_serial(audit_agent, sample_writing_context, sample_drafted_text):
    """run_audit_phase can run in serial mode."""
    with (
        patch.object(audit_agent._fast_screener, "screen_plot", AsyncMock(return_value=(True, "OK"))),
        patch.object(
            audit_agent._logical_auditor, "audit_logical_consistency", AsyncMock(return_value=(True, "OK", 0.9))
        ),
        patch.object(audit_agent._deai_auditor, "audit", AsyncMock(return_value=(True, "OK"))),
        patch.object(
            audit_agent._ability_checker, "audit_ability_consistency", AsyncMock(return_value=(True, "OK", ""))
        ),
        patch.object(audit_agent._plot_monitor, "extract_keywords", AsyncMock(return_value=[])),
        patch.object(audit_agent._plot_monitor, "check_integrity", AsyncMock(return_value=(True, 1.0, MagicMock()))),
    ):
        outcomes, latency = await audit_agent.run_audit_phase(
            sample_writing_context, sample_drafted_text, book_id=1, ep_num=1, parallel=False
        )

    assert len(outcomes) == 6
    assert all(o["passed"] for o in outcomes if o["audit_id"] != "unified_qualitative")


@pytest.mark.asyncio
async def test_run_audit_phase_handles_auditor_exceptions(audit_agent, sample_writing_context, sample_drafted_text):
    """run_audit_phase continues when individual auditors raise exceptions."""
    # Mock unified auditor to return a successful report
    mock_unified_auditor = MagicMock()
    mock_unified_auditor.audit = AsyncMock(
        return_value=MagicMock(
            is_acceptable=True,
            final_score=85.0,
            quantitative_score=80.0,
            qualitative=MagicMock(
                critique="良好なストーリーです。",
                hook_score=85.0,
                emotional_score=90.0,
                character_consistency=80.0,
                overall_score=85.0,
                actionable_patch=None,
            ),
            detected_cliches=[],
            dialogue_ratio=0.0,
            conflicts=[],
        )
    )

    with (
        patch.object(audit_agent._fast_screener, "screen_plot", AsyncMock(side_effect=ValueError("boom"))),
        patch.object(
            audit_agent._logical_auditor, "audit_logical_consistency", AsyncMock(return_value=(True, "OK", 0.9))
        ),
        patch.object(audit_agent._deai_auditor, "audit", AsyncMock(return_value=(True, "OK"))),
        patch.object(
            audit_agent._ability_checker, "audit_ability_consistency", AsyncMock(return_value=(True, "OK", ""))
        ),
        patch.object(audit_agent._plot_monitor, "extract_keywords", AsyncMock(return_value=[])),
        patch.object(audit_agent._plot_monitor, "check_integrity", AsyncMock(return_value=(True, 1.0, MagicMock()))),
        patch.object(audit_agent, "_resolve_unified_auditor", return_value=mock_unified_auditor),
    ):
        outcomes, latency = await audit_agent.run_audit_phase(
            sample_writing_context, sample_drafted_text, book_id=1, ep_num=1
        )

    # One outcome should be failed due to exception
    failed = [o for o in outcomes if not o["passed"]]
    assert len(failed) == 1
    # Find the fast_screen outcome
    fast_screen_outcome = None
    for o in failed:
        if o["audit_id"] == "fast_screen":
            fast_screen_outcome = o
            break
    assert fast_screen_outcome is not None
    assert fast_screen_outcome["feedback"] == "監査器が例外を送出: ValueError: boom"
    assert fast_screen_outcome["error"] == "auditor_exception:ValueError"
    # Others should still have run and passed
    passed = [o for o in outcomes if o["passed"] and o["audit_id"] != "unified_qualitative"]
    assert len(passed) == 4  # logical, deai, ability, causal


# ---------------------------------------------------------------------------
# Gate evaluation tests
# ---------------------------------------------------------------------------


def test_evaluate_gate_all_passed():
    """evaluate_gate with all passed outcomes."""
    outcomes = [
        {
            "audit_id": "fast_screen",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": True,
            "severity": "high",
            "effective_severity": None,
        },
        {
            "audit_id": "logical_consistency",
            "passed": True,
            "score": 100.0,
            "weight": 1.5,
            "blocking": True,
            "severity": "high",
            "effective_severity": None,
        },
        {
            "audit_id": "deai",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": True,
            "severity": "medium",
            "effective_severity": None,
        },
        {
            "audit_id": "ability_consistency",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": True,
            "severity": "medium",
            "effective_severity": None,
        },
        {
            "audit_id": "causal_integrity",
            "passed": True,
            "score": 100.0,
            "weight": 1.5,
            "blocking": True,
            "severity": "high",
            "effective_severity": None,
        },
        {
            "audit_id": "unified_qualitative",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": False,
            "severity": "medium",
            "effective_severity": None,
        },
    ]
    result = evaluate_gate(outcomes)
    assert result["requires_regeneration"] is False
    assert result["aggregate_score"] == 100.0
    assert result["critical_failure"] is False
    assert result["mode"] == "score_aggregation"
    assert result["advisory"] is False


def test_evaluate_gate_one_failed_high():
    """evaluate_gate with one high severity failure."""
    outcomes = [
        {
            "audit_id": "fast_screen",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": True,
            "severity": "high",
            "effective_severity": None,
        },
        {
            "audit_id": "logical_consistency",
            "passed": False,
            "score": 40.0,
            "weight": 1.5,
            "blocking": True,
            "severity": "high",
            "effective_severity": "high",
        },  # 60 penalty -> 40
        {
            "audit_id": "deai",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": True,
            "severity": "medium",
            "effective_severity": None,
        },
        {
            "audit_id": "ability_consistency",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": True,
            "severity": "medium",
            "effective_severity": None,
        },
        {
            "audit_id": "causal_integrity",
            "passed": True,
            "score": 100.0,
            "weight": 1.5,
            "blocking": True,
            "severity": "high",
            "effective_severity": None,
        },
        {
            "audit_id": "unified_qualitative",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": False,
            "severity": "medium",
            "effective_severity": None,
        },
    ]
    result = evaluate_gate(outcomes)
    # Weighted sum: (100*1 + 40*1.5 + 100*1 + 100*1 + 100*1.5) = 100 + 60 + 100 + 100 + 150 = 510
    # Weight total: 1 + 1.5 + 1 + 1 + 1.5 = 6.0
    # Aggregate: 510 / 6.0 = 85.0
    assert result["aggregate_score"] == pytest.approx(85.0, rel=0.001)
    # Threshold is 70.0, aggregate 85.0 > 70, so should NOT regenerate
    assert result["requires_regeneration"] is False
    assert result["critical_failure"] is False


def test_evaluate_gate_critical_failure():
    """evaluate_gate with critical failure (score 0)."""
    outcomes = [
        {
            "audit_id": "fast_screen",
            "passed": False,
            "score": 0.0,
            "weight": 1.0,
            "blocking": True,
            "severity": "critical",
            "effective_severity": "critical",
        },
        {
            "audit_id": "logical_consistency",
            "passed": True,
            "score": 100.0,
            "weight": 1.5,
            "blocking": True,
            "severity": "high",
            "effective_severity": None,
        },
        {
            "audit_id": "deai",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": True,
            "severity": "medium",
            "effective_severity": None,
        },
        {
            "audit_id": "ability_consistency",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": True,
            "severity": "medium",
            "effective_severity": None,
        },
        {
            "audit_id": "causal_integrity",
            "passed": True,
            "score": 100.0,
            "weight": 1.5,
            "blocking": True,
            "severity": "high",
            "effective_severity": None,
        },
        {
            "audit_id": "unified_qualitative",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": False,
            "severity": "medium",
            "effective_severity": None,
        },
    ]
    result = evaluate_gate(outcomes)
    assert result["critical_failure"] is True
    assert result["requires_regeneration"] is True  # critical always triggers regeneration


def test_evaluate_gate_score_gate_disabled(monkeypatch):
    """evaluate_gate falls back to all-or-nothing when score gate disabled."""
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "false")
    outcomes = [
        {
            "audit_id": "fast_screen",
            "passed": False,
            "score": 50.0,
            "weight": 1.0,
            "blocking": True,
            "severity": "high",
            "effective_severity": None,
        },
        {
            "audit_id": "logical_consistency",
            "passed": True,
            "score": 100.0,
            "weight": 1.5,
            "blocking": True,
            "severity": "high",
            "effective_severity": None,
        },
        {
            "audit_id": "deai",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": True,
            "severity": "medium",
            "effective_severity": None,
        },
        {
            "audit_id": "ability_consistency",
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": True,
            "severity": "medium",
            "effective_severity": None,
        },
        {
            "audit_id": "causal_integrity",
            "passed": True,
            "score": 100.0,
            "weight": 1.5,
            "blocking": True,
            "severity": "high",
            "effective_severity": None,
        },
    ]
    result = evaluate_gate(outcomes)
    # With score gate disabled, requires_regeneration = bool(failed)
    assert result["requires_regeneration"] is True  # one failed
    assert result["mode"] == "all_or_nothing"


# ---------------------------------------------------------------------------
# Local patch tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_try_local_patch_disabled(audit_agent):
    """try_local_patch returns None when local patch disabled."""
    with patch("src.agents.audit_agent.is_local_patch_enabled", return_value=False):
        result = await audit_agent.try_local_patch("text", None, None)
        assert result is None


@pytest.mark.asyncio
async def test_try_local_patch_no_drafted_text(audit_agent):
    """try_local_patch returns None when drafted text empty."""
    with patch("src.agents.audit_agent.is_local_patch_enabled", return_value=True):
        result = await audit_agent.try_local_patch("", None, None)
        assert result is None


@pytest.mark.asyncio
async def test_try_local_patch_safe_replacer_success(audit_agent):
    """try_local_patch applies SafeReplacer when mappings exist."""
    # Mock unified report with conflicts that suggest replacements
    unified_report = MagicMock()
    conflict = MagicMock()
    conflict.current_value = "老人"
    conflict.suggested_value = "おじいさん"
    unified_report.conflicts = [conflict]

    with (
        patch("src.agents.audit_agent.is_local_patch_enabled", return_value=True),
        patch("src.agents.audit_agent.is_span_patch_enabled", return_value=False),
        patch("src.agents.audit_agent.is_async_polish_enabled", return_value=False),
        patch("src.services.safe_replace.SafeReplacer") as mock_sr,
    ):
        mock_instance = MagicMock()
        mock_instance.replace.return_value = "主人公はおじいさんに会った。"
        mock_sr.return_value = mock_instance
        result = await audit_agent.try_local_patch("主人公は老人に会った。", unified_report, [])
        assert result is not None
        assert result["strategy"] == "safe_replace"
        assert result["text"] == "主人公はおじいさんに会った。"
        assert result["replacements"] == 1


@pytest.mark.asyncio
async def test_try_local_patch_actionable_patch(audit_agent):
    """try_local_patch applies actionable patch when available."""
    unified_report = MagicMock()
    qualitative = MagicMock()
    qualitative.actionable_patch = "【追加】主人公は決意を新たにした。"
    unified_report.qualitative = qualitative

    with (
        patch("src.agents.audit_agent.is_local_patch_enabled", return_value=True),
        patch("src.agents.audit_agent.is_span_patch_enabled", return_value=False),
        patch("src.agents.audit_agent.is_async_polish_enabled", return_value=False),
        patch("src.services.safe_replace.SafeReplacer"),
        patch("src.generation.local_polish.LocalPolisher"),
    ):
        result = await audit_agent.try_local_patch("主人公は歩いた。", unified_report, [])
        assert result is not None
        assert result["strategy"] == "actionable_patch"
        assert "主人公は歩いた。" in result["text"]
        assert "【追加】主人公は決意を新たにした。" in result["text"]


# ---------------------------------------------------------------------------
# Agent execute tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_agent_execute_missing_artifacts(audit_agent):
    """execute returns error when writing_context or drafted_text missing."""
    ctx = AgentContext(
        book_id=1,
        ep_num=1,
        branch_id=1,
        artifacts={},  # missing required artifacts
    )
    result = await audit_agent.execute(ctx)
    assert result.error is not None
    assert "writing_context and drafted_text are required" in result.error
    assert result.artifacts == {}


@pytest.mark.asyncio
async def test_audit_agent_execute_success(audit_agent, sample_writing_context, sample_drafted_text, mock_repo):
    """execute runs audit and returns success when all pass."""
    # Mock audits to pass
    with (
        patch.object(
            audit_agent,
            "run_audit_phase",
            AsyncMock(
                return_value=(
                    [  # outcomes
                        {
                            "audit_id": "fast_screen",
                            "passed": True,
                            "score": 100.0,
                            "weight": 1.0,
                            "blocking": True,
                            "severity": "high",
                            "effective_severity": None,
                            "feedback": "OK",
                            "learning_adjusted": False,
                            "confidence_adjustment": 0.0,
                            "error": None,
                            "detail": {},
                        },
                        {
                            "audit_id": "logical_consistency",
                            "passed": True,
                            "score": 100.0,
                            "weight": 1.5,
                            "blocking": True,
                            "severity": "high",
                            "effective_severity": None,
                            "feedback": "OK",
                            "learning_adjusted": False,
                            "confidence_adjustment": 0.0,
                            "error": None,
                            "detail": {},
                        },
                        {
                            "audit_id": "deai",
                            "passed": True,
                            "score": 100.0,
                            "weight": 1.0,
                            "blocking": True,
                            "severity": "medium",
                            "effective_severity": None,
                            "feedback": "OK",
                            "learning_adjusted": False,
                            "confidence_adjustment": 0.0,
                            "error": None,
                            "detail": {},
                        },
                        {
                            "audit_id": "ability_consistency",
                            "passed": True,
                            "score": 100.0,
                            "weight": 1.0,
                            "blocking": True,
                            "severity": "medium",
                            "effective_severity": None,
                            "feedback": "OK",
                            "learning_adjusted": False,
                            "confidence_adjustment": 0.0,
                            "error": None,
                            "detail": {},
                        },
                        {
                            "audit_id": "causal_integrity",
                            "passed": True,
                            "score": 100.0,
                            "weight": 1.5,
                            "blocking": True,
                            "severity": "high",
                            "effective_severity": None,
                            "feedback": "OK",
                            "learning_adjusted": False,
                            "confidence_adjustment": 0.0,
                            "error": None,
                            "detail": {},
                        },
                        {
                            "audit_id": "unified_qualitative",
                            "passed": True,
                            "score": 100.0,
                            "weight": 1.0,
                            "blocking": False,
                            "severity": "medium",
                            "effective_severity": None,
                            "feedback": "OK",
                            "learning_adjusted": False,
                            "confidence_adjustment": 0.0,
                            "error": None,
                            "detail": {},
                        },
                    ],
                    0.1,  # latency
                )
            ),
        ),
        patch.object(
            audit_agent,
            "evaluate_gate",
            return_value={
                "mode": "score_aggregation",
                "aggregate_score": 95.0,
                "threshold": 70.0,
                "requires_regeneration": False,
                "critical_failure": False,
                "failed_count": 0,
                "scored_audit_ids": [
                    "fast_screen",
                    "logical_consistency",
                    "deai",
                    "ability_consistency",
                    "causal_integrity",
                ],
                "advisory": False,
                "advisory_reason": "",
            },
        ),
    ):
        ctx = AgentContext(
            book_id=42,
            ep_num=7,
            branch_id=1,
            artifacts={
                "writing_context": sample_writing_context,
                "drafted_text": sample_drafted_text,
                "enriched_text": sample_drafted_text,  # use enriched
            },
        )
        result = await audit_agent.execute(ctx)

    assert result.error is None
    assert result.artifacts["audit_status"] == "passed"
    assert result.artifacts["gate_evaluation"]["requires_regeneration"] is False
    assert result.next_agent == AgentName.ILLUSTRATION


# ---------------------------------------------------------------------------
# Miscellaneous
# ---------------------------------------------------------------------------


def test_audit_criterion_immutable():
    """AuditCriterion is frozen (immutable)."""
    criterion = AuditCriterion(audit_id="test", label="Test", severity="high", learning_key="test")
    with pytest.raises(Exception):  # FrozenInstanceError
        criterion.audit_id = "changed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
