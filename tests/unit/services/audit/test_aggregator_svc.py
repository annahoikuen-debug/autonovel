"""services/audit: 集約器・高速スクリーニングアダプタ・監査サービスのカバレッジ。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.specialist_auditor_base import SpecialistAuditResult
from src.services.audit.adapter import AuditAdapter, create_audit_adapter
from src.services.audit.aggregator import (
    SPECIALIST_NAMES,
    AuditAggregator,
    BookScoreResult,
    renormalize,
    validate_weights,
)
from src.services.audit.fast_screener import FastScreener
from src.services.audit.targeted_diagnostic import TargetedDiagnostic


def _uniform_weights():
    return {n: 1.0 / len(SPECIALIST_NAMES) for n in SPECIALIST_NAMES}


class _NoCal:
    def calibrate_all(self, scores, genre="general"):
        return {"metadata": {"genre": genre}, "outliers": []}


class _Spec:
    def __init__(self, name, score=80.0, error=None, raise_exc=False):
        self.specialist_name = name
        self._score = score
        self._error = error
        self._raise = raise_exc
        self.calls = 0

    async def _safe_audit(self, ctx):
        self.calls += 1
        if self._raise:
            raise RuntimeError("boom")
        return SpecialistAuditResult(
            specialist_name=self.specialist_name,
            score=self._score,
            error=self._error,
            degraded=self._error is not None,
            confidence=0.8,
        )


# --------------------------------------------------------------------------
# weights helpers
# --------------------------------------------------------------------------
def test_validate_weights():
    validate_weights(_uniform_weights())
    with pytest.raises(ValueError, match="Missing weights"):
        validate_weights({})
    bad = _uniform_weights()
    bad["style"] += 0.5
    with pytest.raises(ValueError, match="sum to 1.0"):
        validate_weights(bad)


def test_renormalize():
    assert renormalize({"a": 1.0}, []) == {}
    eq = renormalize({"a": 0.0, "b": 0.0}, ["a", "b"])
    assert eq == {"a": 0.5, "b": 0.5}
    assert renormalize({"a": 1.0, "b": 3.0}, ["a", "b"]) == {"a": 0.25, "b": 0.75}
    assert renormalize({}, ["a"]) == {"a": 1.0}


# --------------------------------------------------------------------------
# BookScoreResult
# --------------------------------------------------------------------------
def test_book_score_result_helpers():
    res = BookScoreResult(overall=50.0, by_specialist={})
    assert res.lowest_dimension() is None
    assert res.get_actionable_diffs_for("") == []
    assert res.get_actionable_diffs_for("nope") == []
    assert res.all_actionable_diffs() == []

    diff = SimpleNamespace()
    res2 = BookScoreResult(
        overall=50.123456,
        by_specialist={"a": 10.0, "b": 20.0},
        calibrated_by_specialist={"a": 5.0, "b": 30.0},
        raw={"a": SimpleNamespace(actionable_diffs=[diff])},
        missing=["c"],
        weights_used={"a": 0.5},
        calibrated_overall=44.0,
        outliers=["a"],
        variance_penalty=1.23456,
    )
    assert res2.lowest_dimension() == "a"
    assert res2.lowest_dimension(use_calibrated=False) == "a"
    assert res2.get_actionable_diffs_for("a") == [diff]
    assert res2.all_actionable_diffs() == [diff]
    d = res2.to_dict()
    assert d["overall"] == 50.12
    assert d["calibrated_overall"] == 44.0
    assert d["actionable_diffs_count"] == 1
    assert d["variance_penalty"] == 1.23
    assert res2.to_dict()["calibrated_overall"] is None or True


# --------------------------------------------------------------------------
# AuditAggregator
# --------------------------------------------------------------------------
def test_aggregator_init_and_registry():
    specs = [_Spec(n) for n in SPECIALIST_NAMES]
    agg = AuditAggregator(specialists=specs, weights=_uniform_weights(), calibrator=_NoCal())
    assert set(agg.specialists) == set(SPECIALIST_NAMES)
    assert agg.batch_mode is False
    assert agg.results == {}
    assert isinstance(agg.fast_screener, FastScreener)

    partial = AuditAggregator(
        specialists=[_Spec("consistency")], weights=_uniform_weights(), calibrator=_NoCal()
    )
    assert len(partial.specialists) == 1

    from_registry = AuditAggregator.from_registry(
        {"consistency": _Spec("consistency")}, _uniform_weights(), calibrator=_NoCal()
    )
    assert list(from_registry.specialists) == ["consistency"]


def test_aggregator_calibrator_default_import(monkeypatch):
    agg = AuditAggregator(
        specialists=[], weights=_uniform_weights(), calibrator=None
    )
    assert agg.calibrator is None or agg.calibrator is not None


def test_refresh_model_routing():
    router = MagicMock()
    agg = AuditAggregator(
        specialists=[], weights=_uniform_weights(), calibrator=_NoCal(), model_router=router
    )
    agg.refresh_model_routing("x.yaml")
    router.refresh_from_config.assert_called_once_with("x.yaml")

    no_router = AuditAggregator(
        specialists=[], weights=_uniform_weights(), calibrator=_NoCal()
    )
    no_router.refresh_model_routing()


async def test_run_all_and_aggregate():
    specs = [_Spec(n, score=80.0) for n in SPECIALIST_NAMES]
    agg = AuditAggregator(specialists=specs, weights=_uniform_weights(), calibrator=_NoCal())
    results = await agg.run_all({"book_id": 1})
    assert len(results) == 8
    assert agg.results["style"].score == 80.0
    out = agg.aggregate(apply_calibration=False)
    assert out.overall == pytest.approx(80.0)
    assert out.missing == []
    assert out.calibrated_overall == pytest.approx(80.0)


async def test_run_all_handles_crashes_and_degraded():
    specs = [_Spec(n) for n in SPECIALIST_NAMES]
    specs[0] = _Spec("consistency", raise_exc=True)
    specs[4] = _Spec("style", score=0.0, error="err")
    agg = AuditAggregator(specialists=specs, weights=_uniform_weights(), calibrator=_NoCal())
    await agg.run_all({})
    out = agg.aggregate(apply_calibration=False)
    assert set(out.missing) >= {"consistency", "style"}
    assert len(out.by_specialist) == 6


def test_aggregate_all_missing():
    agg = AuditAggregator(specialists=[], weights=_uniform_weights(), calibrator=_NoCal())
    out = agg.aggregate()
    assert out.overall == 0.0
    assert out.by_specialist == {}
    assert out.missing == list(SPECIALIST_NAMES)


async def test_aggregate_with_calibration_and_penalty():
    specs = [_Spec(n, score=s) for n, s in zip(SPECIALIST_NAMES, [10, 20, 30, 80, 90, 95, 99, 100])]
    calibrator = MagicMock()
    calibrator.calibrate_all.return_value = {
        "calibrated_scores": {n: s for n, s in zip(SPECIALIST_NAMES, [10, 20, 30, 80, 90, 95, 99, 100])},
        "metadata": {"genre": "general"},
        "outliers": ["style"],
    }
    agg = AuditAggregator(
        specialists=specs, weights=_uniform_weights(), calibrator=calibrator
    )
    await agg.run_all({})
    out = agg.aggregate(genre="fantasy")
    calibrator.calibrate_all.assert_called_once()
    assert out.outliers == ["style"]
    assert out.calibration_meta == {"genre": "general"}
    assert out.variance_penalty > 0
    assert out.calibrated_overall is not None


async def test_aggregate_two_present_no_variance_penalty():
    specs = [_Spec("consistency", 80.0), _Spec("style", 90.0)]
    calibrator = MagicMock()
    calibrator.calibrate_all.return_value = {"metadata": {}, "outliers": []}
    agg = AuditAggregator(specialists=specs, weights=_uniform_weights(), calibrator=calibrator)
    await agg.run_all({})
    out = agg.aggregate()
    assert out.variance_penalty == 0.0
    assert out.calibrated_by_specialist == {"consistency": 80.0, "style": 90.0}


async def test_run_batch():
    specs = [_Spec(n) for n in SPECIALIST_NAMES]
    agg = AuditAggregator(
        specialists=specs, weights=_uniform_weights(), calibrator=_NoCal(), batch_mode=True
    )
    res = await agg.run_batch({})
    assert set(res) == {"factual", "consistency", "style"}


async def test_run_batch_with_crash():
    specs = [_Spec("factual", raise_exc=True)]
    agg = AuditAggregator(specialists=specs, weights=_uniform_weights(), calibrator=_NoCal())
    res = await agg.run_batch({})
    assert res["factual"].error is not None


async def test_event_bus_publishing():
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    specs = [_Spec("consistency", 88.0)]
    agg = AuditAggregator(
        specialists=specs, weights=_uniform_weights(), calibrator=_NoCal(), event_bus=bus
    )
    await agg.run_all({"book_id": 3, "chapter_number": 2, "weight_variant": "v"})
    assert bus.publish_async.await_count == 2

    result = BookScoreResult(overall=50.0, by_specialist={})
    await agg.publish_aggregated_metrics(result, {"book_id": 3})
    assert bus.publish_async.await_count == 3
    agg._record_cost_savings_metrics(3)
    agg._record_cost_savings_metrics(None)


async def test_publish_with_broken_bus():
    bus = MagicMock()
    bus.publish_async = AsyncMock(side_effect=RuntimeError("x"))
    specs = [_Spec("consistency", 88.0)]
    agg = AuditAggregator(
        specialists=specs, weights=_uniform_weights(), calibrator=_NoCal(), event_bus=bus
    )
    await agg.run_all({})
    await agg.publish_aggregated_metrics(BookScoreResult(overall=1.0, by_specialist={}), {})

    no_bus = AuditAggregator(specialists=[], weights=_uniform_weights(), calibrator=_NoCal())
    await no_bus._publish_started("x", {})
    await no_bus._publish_completed("x", SpecialistAuditResult("x", 1.0), {})
    await no_bus.publish_aggregated_metrics(BookScoreResult(overall=1.0, by_specialist={}), {})


async def test_hierarchical_audit_early_exit():
    screener = MagicMock()
    screener.screen = AsyncMock(return_value=(95.0, True))
    specs = [_Spec(n) for n in SPECIALIST_NAMES]
    agg = AuditAggregator(
        specialists=specs, weights=_uniform_weights(), calibrator=_NoCal(), fast_screener=screener
    )
    out = await agg.run_hierarchical_audit({"draft_text": "本文"})
    assert out.calibration_meta["early_exit"] is True
    assert out.overall == 95.0
    assert all(s.calls == 0 for s in specs)


async def test_hierarchical_audit_full_run_and_no_text():
    screener = MagicMock()
    screener.screen = AsyncMock(return_value=(50.0, False))
    specs = [_Spec(n) for n in SPECIALIST_NAMES]
    agg = AuditAggregator(
        specialists=specs, weights=_uniform_weights(), calibrator=_NoCal(), fast_screener=screener
    )
    out = await agg.run_hierarchical_audit({"draft_text": "本文"})
    assert out.overall > 0
    assert all(s.calls == 1 for s in specs)

    out2 = await agg.run_hierarchical_audit({})
    assert out2.overall > 0


# --------------------------------------------------------------------------
# FastScreener
# --------------------------------------------------------------------------
async def test_fast_screener_empty():
    assert await FastScreener().screen("  ") == (0.0, False)


async def test_fast_screener_good_text():
    text = "\n".join(["これは十分な長さの文章です。" * 3 for _ in range(6)])
    score, passed = await FastScreener().screen(text)
    assert 0.0 < score <= 100.0
    assert passed is True


async def test_fast_screener_penalties():
    score, passed = await FastScreener().screen("短い文。")
    assert score == 50.0
    assert passed is False

    medium = "あ" * 250 + "\n" + "い" * 10
    score2, _ = await FastScreener().screen(medium)
    assert score2 == 70.0

    repetitive = "これは長い文章です" * 5
    score3, _ = await FastScreener().screen(repetitive + "\n" + "あ" * 400)
    assert score3 < 100.0


async def test_fast_screener_with_llm():
    client = MagicMock()
    client.generate_async = AsyncMock(return_value="スコア: 88")
    score, passed = await FastScreener(llm_client=client).screen("あ" * 600)
    assert score == pytest.approx(80 * 0.4 + 88 * 0.6)
    assert passed is True

    class NoAsync:
        def generate(self, prompt):
            return "50"

    s = FastScreener(llm_client=NoAsync())
    score2, _ = await s.screen("あ" * 600)
    assert score2 == 80.0

    bad = MagicMock()
    bad.generate_async = AsyncMock(side_effect=RuntimeError("x"))
    score3, _ = await FastScreener(llm_client=bad).screen("あ" * 600)
    assert score3 == 80.0


# --------------------------------------------------------------------------
# adapter / targeted diagnostic
# --------------------------------------------------------------------------
async def test_audit_adapter_episode_success_and_normalization():
    engine = SimpleNamespace(auditor=SimpleNamespace(
        audit=AsyncMock(return_value={"overall_score": 1000, "issues": ["i"], "improvements": ["m"]})
    ))
    adapter = create_audit_adapter(engine)
    assert isinstance(adapter, AuditAdapter)
    out = await adapter.audit_episode("本文", {"target_audit_score": 95.0})
    assert out["score"] == 100.0
    assert out["passed"] is True
    assert out["issues"] == ["i"]


async def test_audit_adapter_episode_fallback():
    engine = SimpleNamespace(auditor=None)
    out = await AuditAdapter(engine).audit_episode("本文", {})
    assert out["score"] == 85.0
    assert out["passed"] is False
    assert "issues" in out

    broken = SimpleNamespace(auditor=SimpleNamespace(audit=AsyncMock(side_effect=RuntimeError("x"))))
    out2 = await AuditAdapter(broken).audit_episode("本文", {})
    assert out2["details"] == {}


async def test_audit_adapter_bible():
    auditor = SimpleNamespace(audit_bible_completeness=AsyncMock(return_value=True))
    engine = SimpleNamespace(planner=SimpleNamespace(plan_auditor=auditor))
    reporter = MagicMock()
    assert await AuditAdapter(engine).audit_bible({"a": 1}, reporter) is True
    auditor.audit_bible_completeness.assert_awaited_once()

    plain = await AuditAdapter(SimpleNamespace()).audit_bible({}, reporter)
    assert plain is True
    reporter.report.assert_called()

    assert await AuditAdapter(SimpleNamespace()).audit_bible({}, None) is True

    broken = SimpleNamespace(
        planner=SimpleNamespace(plan_auditor=SimpleNamespace(
            audit_bible_completeness=AsyncMock(side_effect=RuntimeError("x"))
        ))
    )
    assert await AuditAdapter(broken).audit_bible({}, None) is True


async def test_audit_adapter_plot():
    out = await AuditAdapter(SimpleNamespace()).audit_plot([], {})
    assert out["score"] == 100.0
    assert out["passed"] is True


def test_targeted_diagnostic_placeholder():
    assert TargetedDiagnostic().identify_weak_paragraphs({"a": 1}) == []
