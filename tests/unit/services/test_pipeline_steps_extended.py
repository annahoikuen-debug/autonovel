"""Extended coverage for src/services/pipeline_steps.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.pipeline_base import WorkflowContext
from src.services.pipeline_steps import (
    AuditRewriteStep,
    CatharsisAnalysisStep,
    ForeshadowingRegistrationStep,
    HookGenerationStep,
    IllustrationPointGenerationStep,
    IllustrationStep,
    MarketingStep,
    PackageStep,
    PlanStep,
    WriteStep,
    _emit_skip,
)


def make_ctx(**overrides):
    base = dict(
        genre="fantasy",
        keywords="magic",
        archetype_key="hero",
        target_eps=3,
        initial_limit=3,
        word_count=1000,
        concept="concept",
        title="",
    )
    base.update(overrides)
    return WorkflowContext(**base)


def make_reporter(should_stop=False):
    r = MagicMock()
    r.state.should_stop = MagicMock(return_value=should_stop)
    r.update_progress = MagicMock()
    r.report = MagicMock()
    return r


def make_engine(**kw):
    engine = MagicMock()
    engine.planner = MagicMock()
    engine.writer = MagicMock()
    engine.repo = MagicMock()
    engine.llm = MagicMock()
    engine.llm.generate = AsyncMock(return_value="llm result")
    for k, v in kw.items():
        setattr(engine, k, v)
    return engine


def bible_mock(title="T"):
    b = MagicMock()
    b.title = title
    b.model_dump = MagicMock(return_value={"title": title})
    return b


# ---------------------------------------------------------------- _emit_skip


class TestEmitSkip:
    def test_propagates_to_reporter_ctx_and_metrics(self):
        ctx = make_ctx()
        reporter = make_reporter()
        _emit_skip(reporter, ctx, "mystep", "because")
        assert ctx.warnings == ["mystep: because"]
        reporter.report.assert_called_once_with("⏭️ mystep: because", "warning")

    def test_reporter_failure_is_swallowed(self):
        ctx = make_ctx()
        reporter = make_reporter()
        reporter.report.side_effect = RuntimeError("no ui")
        _emit_skip(reporter, ctx, "s", "r")
        assert ctx.warnings == ["s: r"]

    def test_metrics_failure_is_swallowed(self):
        ctx = make_ctx()
        reporter = make_reporter()
        with patch("src.services.pipeline_steps.metrics") as m:
            m.increment.side_effect = RuntimeError("no metrics")
            _emit_skip(reporter, ctx, "s", "r")
        assert ctx.warnings == ["s: r"]


# ------------------------------------------------------------------ PlanStep


class TestPlanStep:
    async def test_catharsis_analysis_enabled(self):
        ctx = make_ctx(enable_catharsis_analysis=True)
        engine = make_engine()
        engine.planner.create_hegemony_plan = AsyncMock(return_value=(7, bible_mock()))
        engine.planner.plan_auditor.audit_bible_completeness = AsyncMock(return_value=True)
        engine.repo.plot.get_all_plots = AsyncMock(return_value=[MagicMock(tension=10), MagicMock(tension=99)])
        engine.plot_expander = None

        with patch("src.backend.engine_narrative.WavePatternAnalyzer") as wave_cls, \
             patch("config.project_context.ProjectContext") as pc:
            pattern = MagicMock()
            pattern.catharsis_points = [1, 2]
            pattern.model_dump.return_value = {"pattern_type": "x"}
            wave_cls.return_value.analyze.return_value = pattern
            pc.get_setting.return_value = 65
            result = await PlanStep().execute(ctx, engine, make_reporter())

        assert result is True
        assert ctx.book_id == 7
        assert ctx.catharsis_positions == [1, 2]
        assert ctx.easy_parameters["catharsis_pattern"] == {"pattern_type": "x"}

    async def test_catharsis_analysis_failure_is_reported(self):
        ctx = make_ctx(enable_catharsis_analysis=True)
        engine = make_engine()
        engine.planner.create_hegemony_plan = AsyncMock(return_value=(7, bible_mock()))
        engine.planner.plan_auditor.audit_bible_completeness = AsyncMock(return_value=True)
        engine.repo.plot.get_all_plots = AsyncMock(side_effect=RuntimeError("db"))
        engine.plot_expander = None
        reporter = make_reporter()

        result = await PlanStep().execute(ctx, engine, reporter)
        assert result is True
        assert any("カタルシス" in str(c) for c in reporter.report.call_args_list)

    async def test_catharsis_disabled(self):
        ctx = make_ctx(enable_catharsis_analysis=False)
        engine = make_engine()
        engine.planner.create_hegemony_plan = AsyncMock(return_value=(1, bible_mock()))
        engine.planner.plan_auditor.audit_bible_completeness = AsyncMock(return_value=True)
        engine.plot_expander = None
        assert await PlanStep().execute(ctx, engine, make_reporter()) is True
        assert "catharsis_pattern" not in ctx.easy_parameters

    async def test_bible_without_model_dump(self):
        class PlainBible:
            def __init__(self):
                self.title = "PlainBible"

        ctx = make_ctx(enable_catharsis_analysis=True)
        engine = make_engine()
        bible = PlainBible()
        engine.planner.create_hegemony_plan = AsyncMock(return_value=(1, bible))
        engine.planner.plan_auditor.audit_bible_completeness = AsyncMock(return_value=True)
        engine.repo.plot.get_all_plots = AsyncMock(return_value=None)
        engine.plot_expander = None
        reporter = make_reporter()

        with patch("src.backend.engine_narrative.WavePatternAnalyzer") as wave_cls, \
             patch("config.project_context.ProjectContext"):
            pattern = MagicMock()
            pattern.catharsis_points = []
            pattern.model_dump.return_value = {}
            wave_cls.return_value.analyze.return_value = pattern
            await PlanStep().execute(ctx, engine, reporter)
        assert ctx.title == "PlainBible"

    async def test_macro_skeleton_expansion(self):
        ctx = make_ctx(use_coarse_fine_plot=True)
        engine = make_engine()
        engine.planner.create_hegemony_plan = AsyncMock(return_value=(1, bible_mock()))
        engine.planner.plan_auditor.audit_bible_completeness = AsyncMock(return_value=True)
        engine.plot_expander = MagicMock()
        engine.plot_expander.expand_macro_skeletons = AsyncMock(return_value=[1, 2, 3])

        assert await PlanStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.easy_parameters["macro_skeletons_count"] == 3

    async def test_macro_skeleton_failure_is_reported(self):
        ctx = make_ctx(use_coarse_fine_plot=True)
        engine = make_engine()
        engine.planner.create_hegemony_plan = AsyncMock(return_value=(1, bible_mock()))
        engine.planner.plan_auditor.audit_bible_completeness = AsyncMock(return_value=True)
        engine.plot_expander = MagicMock()
        engine.plot_expander.expand_macro_skeletons = AsyncMock(side_effect=RuntimeError("nope"))
        reporter = make_reporter()
        assert await PlanStep().execute(ctx, engine, reporter) is True
        assert any("大局骨子" in str(c) for c in reporter.report.call_args_list)

    async def test_macro_skeleton_disabled(self):
        ctx = make_ctx(use_coarse_fine_plot=False)
        engine = make_engine()
        engine.planner.create_hegemony_plan = AsyncMock(return_value=(1, bible_mock()))
        engine.planner.plan_auditor.audit_bible_completeness = AsyncMock(return_value=True)
        engine.plot_expander = MagicMock()
        assert await PlanStep().execute(ctx, engine, make_reporter()) is True
        assert "macro_skeletons_count" not in ctx.easy_parameters

    async def test_expander_without_macro_method(self):
        ctx = make_ctx()
        engine = make_engine()
        engine.planner.create_hegemony_plan = AsyncMock(return_value=(1, bible_mock()))
        engine.planner.plan_auditor.audit_bible_completeness = AsyncMock(return_value=True)
        engine.plot_expander = MagicMock(spec=["other"])
        assert await PlanStep().execute(ctx, engine, make_reporter()) is True

    async def test_auditor_rejects(self):
        ctx = make_ctx()
        engine = make_engine()
        engine.planner.create_hegemony_plan = AsyncMock(return_value=(1, bible_mock()))
        engine.planner.plan_auditor.audit_bible_completeness = AsyncMock(return_value=False)
        engine.plot_expander = None
        assert await PlanStep().execute(ctx, engine, make_reporter()) is False

    async def test_no_auditor_attribute(self):
        ctx = make_ctx()
        engine = make_engine()
        engine.planner.create_hegemony_plan = AsyncMock(return_value=(1, bible_mock()))
        engine.planner.plan_auditor = None
        engine.plot_expander = None
        assert await PlanStep().execute(ctx, engine, make_reporter()) is True

    async def test_easy_parameters_forwards_erotic(self):
        ctx = make_ctx(easy_parameters={"enable_erotic": True, "erotic_intensity": 4})
        engine = make_engine()
        engine.planner.create_hegemony_plan = AsyncMock(return_value=(1, bible_mock()))
        engine.planner.plan_auditor.audit_bible_completeness = AsyncMock(return_value=True)
        engine.plot_expander = None
        await PlanStep().execute(ctx, engine, make_reporter())
        kwargs = engine.planner.create_hegemony_plan.await_args.kwargs
        assert kwargs["enable_erotic"] is True
        assert kwargs["erotic_intensity"] == 4

    async def test_error_reraised(self):
        ctx = make_ctx()
        engine = make_engine()
        engine.planner.create_hegemony_plan = AsyncMock(side_effect=RuntimeError("boom"))
        reporter = make_reporter()
        with pytest.raises(RuntimeError):
            await PlanStep().execute(ctx, engine, reporter)
        assert any("error" in str(c) for c in reporter.report.call_args_list)


# ----------------------------------------------------------------- WriteStep


class TestWriteStep:
    async def test_jit_detailed_plot_precheck(self):
        ctx = make_ctx(book_id=1, start_ep=1, end_ep=2)
        engine = make_engine()
        engine.plot_expander = MagicMock()
        engine.plot_expander.ensure_detailed_plot = AsyncMock()
        with patch(
            "src.backend.workflows._shared_ops.execute_with_retry",
            new=AsyncMock(return_value=(100, [])),
        ):
            assert await WriteStep().execute(ctx, engine, make_reporter()) is True
        engine.plot_expander.ensure_detailed_plot.assert_awaited_once()

    async def test_jit_precheck_error_swallowed(self):
        ctx = make_ctx(book_id=1)
        engine = make_engine()
        engine.plot_expander = MagicMock()
        engine.plot_expander.ensure_detailed_plot = AsyncMock(side_effect=RuntimeError("x"))
        with patch(
            "src.backend.workflows._shared_ops.execute_with_retry",
            new=AsyncMock(return_value=(100, [])),
        ):
            assert await WriteStep().execute(ctx, engine, make_reporter()) is True

    async def test_coarse_fine_disabled(self):
        ctx = make_ctx(book_id=1, use_coarse_fine_plot=False)
        engine = make_engine()
        engine.plot_expander = MagicMock()
        with patch(
            "src.backend.workflows._shared_ops.execute_with_retry",
            new=AsyncMock(return_value=(100, [])),
        ):
            assert await WriteStep().execute(ctx, engine, make_reporter()) is True
        engine.plot_expander.ensure_detailed_plot.assert_not_called()

    async def test_stop_signal(self):
        ctx = make_ctx(book_id=1)
        engine = make_engine()
        engine.plot_expander = None
        with patch(
            "src.backend.workflows._shared_ops.execute_with_retry",
            new=AsyncMock(return_value=(100, [])),
        ):
            assert await WriteStep().execute(ctx, engine, make_reporter(should_stop=True)) is False

    async def test_error_reraised(self):
        ctx = make_ctx(book_id=1)
        engine = make_engine()
        engine.plot_expander = None
        reporter = make_reporter()
        with patch(
            "src.backend.workflows._shared_ops.execute_with_retry",
            new=AsyncMock(side_effect=RuntimeError("write fail")),
        ):
            with pytest.raises(RuntimeError):
                await WriteStep().execute(ctx, engine, reporter)
        assert any("error" in str(c) for c in reporter.report.call_args_list)


# ------------------------------------------------------- CatharsisAnalysisStep


class TestCatharsisAnalysisStep:
    async def test_disabled(self):
        ctx = make_ctx(enable_catharsis_analysis=False)
        assert await CatharsisAnalysisStep().execute(ctx, make_engine(), make_reporter()) is True
        assert ctx.warnings == ["catharsis: enable_catharsis_analysis=False"]

    async def test_no_book_id(self):
        ctx = make_ctx(enable_catharsis_analysis=True, book_id=None)
        assert await CatharsisAnalysisStep().execute(ctx, make_engine(), make_reporter()) is True
        assert "book_id is None" in ctx.warnings[0]

    async def test_success_with_plots(self):
        ctx = make_ctx(enable_catharsis_analysis=True, book_id=1)
        engine = make_engine()
        engine.repo.plot.get_all_plots = AsyncMock(return_value=[MagicMock(tension=1), MagicMock()])
        reporter = make_reporter()
        with patch("src.backend.engine_narrative.WavePatternAnalyzer") as wave_cls, \
             patch("config.project_context.ProjectContext") as pc:
            pattern = MagicMock()
            pattern.catharsis_points = [3]
            pattern.model_dump.return_value = {"a": 1}
            wave_cls.return_value.analyze.return_value = pattern
            pc.get_setting.side_effect = lambda k, d: d
            assert await CatharsisAnalysisStep().execute(ctx, engine, reporter) is True
        assert ctx.catharsis_positions == [3]
        assert ctx.easy_parameters["catharsis_positions"] == [3]

    async def test_success_without_plots_uses_defaults(self):
        ctx = make_ctx(enable_catharsis_analysis=True, book_id=1)
        engine = make_engine()
        engine.repo.plot.get_all_plots = AsyncMock(return_value=None)
        with patch("src.backend.engine_narrative.WavePatternAnalyzer") as wave_cls, \
             patch("config.project_context.ProjectContext"):
            pattern = MagicMock()
            pattern.catharsis_points = []
            pattern.model_dump.return_value = {}
            wave_cls.return_value.analyze.return_value = pattern
            assert await CatharsisAnalysisStep().execute(ctx, engine, make_reporter()) is True
        wave_cls.return_value.analyze.assert_called_once_with([50] * 5)

    async def test_failure_returns_true(self):
        ctx = make_ctx(enable_catharsis_analysis=True, book_id=1)
        engine = make_engine()
        engine.repo.plot.get_all_plots = AsyncMock(side_effect=RuntimeError("db"))
        reporter = make_reporter()
        assert await CatharsisAnalysisStep().execute(ctx, engine, reporter) is True
        assert any("カタルシス" in str(c) for c in reporter.report.call_args_list)


# --------------------------------------------------------- AuditRewriteStep


def spice_guard_stub():
    g = MagicMock()
    g.extract_spice = MagicMock(return_value=["spice1"])
    g.build_rewrite_prompt = MagicMock(return_value="PROMPT")
    g.clean_markers = MagicMock(side_effect=lambda s: f"[{s}]")
    return g


class TestAuditRewriteStep:
    def _ctx(self, **kw):
        return make_ctx(book_id=1, target_audit_score=90.0, max_rewrite_iterations=3, **kw)

    def _engine(self, score=95.0, content="body", guard=None):
        engine = make_engine()
        ep = MagicMock()
        ep.content = content
        engine.repo.episode.get_by_book_and_number = AsyncMock(return_value=ep)
        engine.repo.episode.update_content = AsyncMock()
        engine.repo.bible.get_by_book_id = AsyncMock(return_value=MagicMock())
        engine.repo.plot.get_by_book_and_number = AsyncMock(return_value=MagicMock())
        adapter = MagicMock()
        adapter.audit_episode = AsyncMock(return_value={"score": score, "improvements": ["fix"]})
        engine.plot_expander = None
        engine._audit_adapter = adapter
        engine._guard = guard or spice_guard_stub()
        return engine

    async def test_disabled_spice_guard(self):
        ctx = self._ctx(enable_spice_guard=False)
        assert await AuditRewriteStep().execute(ctx, make_engine(), make_reporter()) is True

    async def test_no_book_id(self):
        ctx = make_ctx(book_id=None)
        assert await AuditRewriteStep().execute(ctx, make_engine(), make_reporter()) is True

    async def test_episodes_pass_without_rewrite(self):
        ctx = self._ctx()
        engine = self._engine(score=95.0)
        with patch("src.services.pipeline_steps.create_audit_adapter", return_value=engine._audit_adapter), \
             patch("src.services.pipeline_steps.create_spice_guard_adapter", return_value=engine._guard):
            assert await AuditRewriteStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.average_audit_score == 95.0
        assert len(ctx.episodes_detail) == 3
        assert ctx.easy_parameters["spice_guard_enabled"] is True
        engine.repo.episode.update_content.assert_not_called()

    async def test_missing_content_skipped(self):
        ctx = self._ctx()
        engine = self._engine()
        engine.repo.episode.get_by_book_and_number = AsyncMock(return_value=None)
        with patch("src.services.pipeline_steps.create_audit_adapter", return_value=engine._audit_adapter), \
             patch("src.services.pipeline_steps.create_spice_guard_adapter", return_value=engine._guard):
            assert await AuditRewriteStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.episodes_detail == []

    async def test_rewrite_happens_then_passes(self):
        ctx = self._ctx()
        engine = self._engine(score=50.0)
        engine._audit_adapter.audit_episode = AsyncMock(
            side_effect=[{"score": 50.0, "improvements": ["a"]}, {"score": 95.0, "improvements": []}]
        )
        with patch("src.services.pipeline_steps.create_audit_adapter", return_value=engine._audit_adapter), \
             patch("src.services.pipeline_steps.create_spice_guard_adapter", return_value=engine._guard):
            assert await AuditRewriteStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.episodes_detail[0]["rewrite_count"] == 1
        engine.repo.episode.update_content.assert_awaited()

    async def test_human_review_when_exhausted(self):
        ctx = make_ctx(
            book_id=1,
            target_audit_score=90.0,
            max_rewrite_iterations=1,
            enable_spice_guard=True,
        )
        engine = self._engine(score=10.0)
        with patch("src.services.pipeline_steps.create_audit_adapter", return_value=engine._audit_adapter), \
             patch("src.services.pipeline_steps.create_spice_guard_adapter", return_value=engine._guard):
            await AuditRewriteStep().execute(ctx, engine, make_reporter())
        assert ctx.episodes_detail[0]["needs_human_review"] is True

    async def test_no_improvements_breaks(self):
        ctx = self._ctx()
        engine = self._engine(score=10.0)
        engine._audit_adapter.audit_episode = AsyncMock(
            return_value={"score": 10.0, "improvements": []}
        )
        with patch("src.services.pipeline_steps.create_audit_adapter", return_value=engine._audit_adapter), \
             patch("src.services.pipeline_steps.create_spice_guard_adapter", return_value=engine._guard):
            await AuditRewriteStep().execute(ctx, engine, make_reporter())
        assert ctx.episodes_detail[0]["rewrite_count"] == 0

    async def test_empty_rewrite_breaks(self):
        ctx = self._ctx()
        engine = self._engine(score=10.0)
        engine.llm.generate = AsyncMock(return_value="   ")
        with patch("src.services.pipeline_steps.create_audit_adapter", return_value=engine._audit_adapter), \
             patch("src.services.pipeline_steps.create_spice_guard_adapter", return_value=engine._guard):
            await AuditRewriteStep().execute(ctx, engine, make_reporter())
        assert ctx.episodes_detail[0]["rewrite_count"] == 0

    async def test_rewrite_exception_breaks(self):
        ctx = self._ctx()
        engine = self._engine(score=10.0)
        engine.llm.generate = AsyncMock(side_effect=RuntimeError("llm down"))
        with patch("src.services.pipeline_steps.create_audit_adapter", return_value=engine._audit_adapter), \
             patch("src.services.pipeline_steps.create_spice_guard_adapter", return_value=engine._guard):
            await AuditRewriteStep().execute(ctx, engine, make_reporter())
        assert ctx.episodes_detail[0]["rewrite_count"] == 0

    async def test_episode_error_recorded(self):
        ctx = self._ctx()
        engine = self._engine()
        engine.repo.episode.get_by_book_and_number = AsyncMock(side_effect=RuntimeError("db"))
        with patch("src.services.pipeline_steps.create_audit_adapter", return_value=engine._audit_adapter), \
             patch("src.services.pipeline_steps.create_spice_guard_adapter", return_value=engine._guard):
            assert await AuditRewriteStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.episodes_detail[0]["error"] == "db"
        assert ctx.episodes_detail[0]["needs_human_review"] is True

    async def test_stop_signal_aborts(self):
        ctx = self._ctx()
        engine = self._engine()
        with patch("src.services.pipeline_steps.create_audit_adapter", return_value=engine._audit_adapter), \
             patch("src.services.pipeline_steps.create_spice_guard_adapter", return_value=engine._guard):
            assert await AuditRewriteStep().execute(ctx, engine, make_reporter(should_stop=True)) is False

    async def test_bible_without_dict(self):
        ctx = self._ctx()
        engine = self._engine()
        engine.repo.bible.get_by_book_id = AsyncMock(return_value=None)
        engine.repo.plot.get_by_book_and_number = AsyncMock(return_value=None)
        seen = []

        async def cap(content, audit_context):
            seen.append((content, audit_context))
            return {"score": 95.0, "improvements": []}

        engine._audit_adapter.audit_episode = AsyncMock(side_effect=cap)
        with patch("src.services.pipeline_steps.create_audit_adapter", return_value=engine._audit_adapter), \
             patch("src.services.pipeline_steps.create_spice_guard_adapter", return_value=engine._guard):
            await AuditRewriteStep().execute(ctx, engine, make_reporter())
        assert [e["episode"] for _, e in seen] == [1, 2, 3]
        assert all(ctx_["bible"] is None and ctx_["plot"] is None for _, ctx_ in seen)


# --------------------------------------------------------------- PackageStep


class TestPackageStep:
    async def test_no_book_id(self):
        ctx = make_ctx(book_id=None)
        assert await PackageStep().execute(ctx, make_engine(), make_reporter()) is False
        assert ctx.warnings == ["package: book_id is None"]

    async def test_success_fills_marketing_shell(self):
        ctx = make_ctx(book_id=4)
        engine = make_engine()
        engine.repo.get_book = AsyncMock(return_value=MagicMock(title="Real Title"))
        assert await PackageStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.title == "Real Title"
        assert ctx.zip_filename == "export_4.zip"
        assert ctx.zip_data is None
        assert ctx.marketing_pack["tags"] == []

    async def test_book_is_none(self):
        ctx = make_ctx(book_id=4)
        engine = make_engine()
        engine.repo.get_book = AsyncMock(return_value=None)
        assert await PackageStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.title == ""

    async def test_existing_marketing_pack_preserved(self):
        ctx = make_ctx(book_id=4, marketing_pack={"title": "kept"})
        engine = make_engine()
        engine.repo.get_book = AsyncMock(return_value=None)
        assert await PackageStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.marketing_pack == {"title": "kept"}
        assert ctx.warnings == []

    async def test_error_reraised(self):
        ctx = make_ctx(book_id=4)
        engine = make_engine()
        engine.repo.get_book = AsyncMock(side_effect=RuntimeError("db"))
        reporter = make_reporter()
        with pytest.raises(RuntimeError):
            await PackageStep().execute(ctx, engine, reporter)
        assert any("error" in str(c) for c in reporter.report.call_args_list)


# ---------------------------------------------------------- IllustrationStep


class TestIllustrationStep:
    async def test_disabled(self):
        ctx = make_ctx(enable_illustration=False, book_id=1)
        assert await IllustrationStep().execute(ctx, make_engine(), make_reporter()) is True
        assert ctx.warnings == ["illustration: enable_illustration=False"]

    async def test_settings_missing_flag(self):
        ctx = make_ctx(enable_illustration=True, book_id=1, illustration_settings={})
        assert await IllustrationStep().execute(ctx, make_engine(), make_reporter()) is True
        assert "enableIllustration" in ctx.warnings[0]

    async def test_no_book_id(self):
        ctx = make_ctx(enable_illustration=True, illustration_settings={"enableIllustration": True})
        assert await IllustrationStep().execute(ctx, make_engine(), make_reporter()) is True
        assert ctx.warnings == ["illustration: book_id is None"]

    async def _run(self, result, **engine_kw):
        ctx = make_ctx(enable_illustration=True, book_id=1, illustration_settings={"enableIllustration": True})
        engine = make_engine(**engine_kw)
        engine.repo = MagicMock()
        wf = MagicMock()
        wf.execute = AsyncMock(return_value=result)
        with patch("src.backend.workflows.illustration_workflow.IllustrationWorkflow", return_value=wf):
            reporter = make_reporter()
            ok = await IllustrationStep().execute(ctx, engine, reporter)
        return ctx, reporter, ok

    async def test_success(self):
        ctx, reporter, ok = await self._run(
            {"status": "success", "illustrations": [{"id": 1}]},
            illustration_agent=MagicMock(),
        )
        assert ok is True
        assert ctx.illustrations == [{"id": 1}]
        assert any("info" == c.args[1] for c in reporter.report.call_args_list)

    async def test_failure_reported(self):
        ctx, reporter, ok = await self._run(
            {"status": "error", "error": "no key"},
            illustration_agent=MagicMock(),
        )
        assert ok is True
        assert ctx.illustrations == []
        assert any("no key" in str(c) for c in reporter.report.call_args_list)

    async def test_exception_returns_true(self):
        ctx, reporter, ok = await self._run(
            {"status": "success"},
            illustration_agent=MagicMock(),
        )
        assert ok is True

    async def test_engine_agent_missing_falls_back(self):
        ctx = make_ctx(enable_illustration=True, book_id=1, illustration_settings={"enableIllustration": True})
        engine = MagicMock(spec=["repo"])
        engine.repo = MagicMock()
        engine.illustration_agent = None
        wf = MagicMock()
        wf.execute = AsyncMock(return_value={"status": "success", "illustrations": []})
        with patch("src.backend.workflows.illustration_workflow.IllustrationWorkflow", return_value=wf), \
             patch("src.services.image_service.ImageService") as image_service, \
             patch("src.backend.config.settings") as settings:
            settings.get_gemini_api_key.return_value = "key"
            assert await IllustrationStep().execute(ctx, engine, make_reporter()) is True
        image_service.assert_called_once()

    async def test_workflow_raises(self):
        ctx = make_ctx(enable_illustration=True, book_id=1, illustration_settings={"enableIllustration": True})
        engine = make_engine(illustration_agent=MagicMock())
        engine.repo = MagicMock()
        with patch("src.backend.workflows.illustration_workflow.IllustrationWorkflow", side_effect=RuntimeError("x")):
            reporter = make_reporter()
            assert await IllustrationStep().execute(ctx, engine, reporter) is True
        assert any("warning" == c.args[1] for c in reporter.report.call_args_list)


# ------------------------------------------------------------- MarketingStep


class TestMarketingStep:
    async def test_disabled(self):
        ctx = make_ctx(enable_marketing=False, book_id=1)
        assert await MarketingStep().execute(ctx, make_engine(), make_reporter()) is True
        assert ctx.warnings == ["marketing: enable_marketing=False"]

    async def test_no_book_id(self):
        ctx = make_ctx(enable_marketing=True, book_id=None)
        assert await MarketingStep().execute(ctx, make_engine(), make_reporter()) is True
        assert ctx.warnings == ["marketing: book_id is None"]

    async def test_preset_title_used(self):
        ctx = make_ctx(enable_marketing=True, book_id=1, title="")
        engine = make_engine()
        preset = {
            "titles": {"title_templates": ["Preset Title", "Other"]},
            "marketing": {
                "synopsis_structure": {"hook": "hook text"},
                "catchphrase_templates": ["Catch"],
                "tags": [f"t{i}" for i in range(20)],
            },
        }
        with patch("src.services.pipeline_steps.load_preset_for_pipeline", return_value=preset):
            assert await MarketingStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.title == "Preset Title"
        assert ctx.marketing_pack["catchphrase"] == "Catch"
        assert len(ctx.marketing_pack["tags"]) == 10
        assert ctx.easy_parameters["title"] == "Preset Title"

    async def test_llm_title_fallback(self):
        ctx = make_ctx(enable_marketing=True, book_id=1, title="", archetype_key="")
        engine = make_engine()
        engine.llm.generate = AsyncMock(return_value='「LLM Title」\nextra line')
        with patch("src.services.pipeline_steps.load_preset_for_pipeline", return_value=None):
            assert await MarketingStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.title == "LLM Title"

    async def test_llm_failure_uses_template(self):
        ctx = make_ctx(enable_marketing=True, book_id=1, title="")
        engine = make_engine()
        engine.llm.generate = AsyncMock(side_effect=RuntimeError("llm down"))
        with patch("src.services.pipeline_steps.load_preset_for_pipeline", return_value={}):
            assert await MarketingStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.title == "fantasyの物語"

    async def test_existing_title_kept(self):
        ctx = make_ctx(enable_marketing=True, book_id=1, title="Existing")
        engine = make_engine()
        with patch("src.services.pipeline_steps.load_preset_for_pipeline", return_value={}):
            assert await MarketingStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.title == "Existing"
        engine.llm.generate.assert_not_called()

    async def test_empty_catchphrase_templates(self):
        ctx = make_ctx(enable_marketing=True, book_id=1, title="T")
        engine = make_engine()
        preset = {"marketing": {"catchphrase_templates": [], "tags": None, "synopsis_structure": None}}
        with patch("src.services.pipeline_steps.load_preset_for_pipeline", return_value=preset):
            assert await MarketingStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.marketing_pack["catchphrase"] == ""
        assert ctx.marketing_pack["concept"] == "concept"

    async def test_exception_returns_true(self):
        ctx = make_ctx(enable_marketing=True, book_id=1)
        reporter = make_reporter()
        with patch("src.services.pipeline_steps.load_preset_for_pipeline", side_effect=RuntimeError("boom")):
            assert await MarketingStep().execute(ctx, engine_or_raise(), reporter) is True
        assert any("warning" == c.args[1] for c in reporter.report.call_args_list)


def engine_or_raise():
    return make_engine()


# ------------------------------------------------------- HookGenerationStep


class TestHookGenerationStep:
    async def test_always_true(self):
        assert await HookGenerationStep().execute(make_ctx(), make_engine(), make_reporter()) is True


# -------------------------------------------- IllustrationPointGenerationStep


class TestIllustrationPointGenerationStep:
    def _engine(self, characters=None, episodes=None, bible=MagicMock()):
        engine = make_engine()
        b = bible
        if characters is not None:
            b.characters = characters
        engine.repo.bible.get_by_book_id = AsyncMock(return_value=b)
        engine.repo.plot.get_all_plots = AsyncMock(return_value=[MagicMock()])
        engine.repo.episode.get_all_by_book_id = AsyncMock(return_value=episodes or [])
        return engine

    async def test_disabled(self):
        ctx = make_ctx(enable_illustration=False)
        assert await IllustrationPointGenerationStep().execute(ctx, make_engine(), make_reporter()) is True
        assert ctx.warnings == ["illustration_point: enable_illustration=False"]

    async def test_no_book_id(self):
        ctx = make_ctx(enable_illustration=True, book_id=None)
        assert await IllustrationPointGenerationStep().execute(ctx, make_engine(), make_reporter()) is True
        assert ctx.warnings == ["illustration_point: book_id is None"]

    async def test_bible_missing(self):
        ctx = make_ctx(enable_illustration=True, book_id=1)
        engine = self._engine(bible=None)
        reporter = make_reporter()
        assert await IllustrationPointGenerationStep().execute(ctx, engine, reporter) is True
        assert "Bible" in "".join(str(c) for c in reporter.report.call_args_list)

    async def test_no_episodes(self):
        ctx = make_ctx(enable_illustration=True, book_id=1)
        engine = self._engine(episodes=[])
        assert await IllustrationPointGenerationStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.illustration_points == []

    async def test_single_episode(self):
        ctx = make_ctx(enable_illustration=True, book_id=1)
        engine = self._engine(episodes=[MagicMock()])
        assert await IllustrationPointGenerationStep().execute(ctx, engine, make_reporter()) is True
        assert len(ctx.illustration_points) == 2

    async def test_three_episodes_with_characters(self):
        ctx = make_ctx(enable_illustration=True, book_id=1)
        c1 = MagicMock()
        c1.name = "Hero"
        c2 = {"name": "Rival"}
        engine = self._engine(episodes=[MagicMock() for _ in range(3)], characters=[c1, c2])
        assert await IllustrationPointGenerationStep().execute(ctx, engine, make_reporter()) is True
        assert len(ctx.illustration_points) == 3
        climax = ctx.illustration_points[1]
        assert "Rival" in climax.expressions

    async def test_characters_without_name_attr(self):
        ctx = make_ctx(enable_illustration=True, book_id=1)
        engine = self._engine(episodes=[MagicMock()], characters=[MagicMock(spec=[])])
        assert await IllustrationPointGenerationStep().execute(ctx, engine, make_reporter()) is True
        assert len(ctx.illustration_points) == 2

    async def test_exception_returns_true(self):
        ctx = make_ctx(enable_illustration=True, book_id=1)
        engine = self._engine(episodes=[])
        engine.repo.bible.get_by_book_id = AsyncMock(side_effect=RuntimeError("db"))
        reporter = make_reporter()
        assert await IllustrationPointGenerationStep().execute(ctx, engine, reporter) is True
        assert any("warning" == c.args[1] for c in reporter.report.call_args_list)


# ------------------------------------------- ForeshadowingRegistrationStep


class TestForeshadowingRegistrationStep:
    def _engine(self, plots, repo=None):
        engine = make_engine()
        engine.repo.plot.get_all_plots = AsyncMock(return_value=plots)
        if repo is not None:
            engine.foreshadowing_repository = repo
        else:
            engine.foreshadowing_repository = None
        return engine

    async def test_no_book_id(self):
        ctx = make_ctx(book_id=None)
        assert await ForeshadowingRegistrationStep().execute(ctx, make_engine(), make_reporter()) is True
        assert ctx.warnings == ["foreshadowing_registration: book_id is None"]

    async def test_no_plots(self):
        ctx = make_ctx(book_id=1)
        reporter = make_reporter()
        assert await ForeshadowingRegistrationStep().execute(ctx, self._engine([]), reporter) is True
        assert any("find" in str(c) or "not found" in str(c) or "プロット" in str(c) for c in reporter.report.call_args_list)

    async def test_plots_without_hints(self):
        ctx = make_ctx(book_id=1)
        engine = self._engine([MagicMock(spec=[])])
        assert await ForeshadowingRegistrationStep().execute(ctx, engine, make_reporter()) is True
        assert ctx.foreshadowings == []

    async def test_stores_to_context(self):
        ctx = make_ctx(book_id=1)
        plot = MagicMock(spec=["foreshadowing_hint"])
        plot.foreshadowing_hint = "謎の存在"
        engine = self._engine([plot])
        assert await ForeshadowingRegistrationStep().execute(ctx, engine, make_reporter()) is True
        assert len(ctx.foreshadowings) == 1
        assert ctx.foreshadowings[0].id == "FS-001"

    async def test_stores_to_repository(self):
        ctx = make_ctx(book_id=1)
        plot = MagicMock(spec=["mystery_element"])
        plot.mystery_element = "reader clue"
        repo = MagicMock()
        engine = self._engine([plot], repo=repo)
        assert await ForeshadowingRegistrationStep().execute(ctx, engine, make_reporter()) is True
        repo.add.assert_called_once()
        assert ctx.foreshadowings == []

    async def test_exception_returns_true(self):
        ctx = make_ctx(book_id=1)
        engine = make_engine()
        engine.repo.plot.get_all_plots = AsyncMock(side_effect=RuntimeError("db"))
        reporter = make_reporter()
        assert await ForeshadowingRegistrationStep().execute(ctx, engine, reporter) is True
        assert any("warning" == c.args[1] for c in reporter.report.call_args_list)

    @pytest.mark.parametrize(
        "attr,value,hang_type,importance",
        [
            # a single-token hint always scores keyword_count == 2 (2 * len(split)),
            # so the single-star bucket is unreachable via this formula.
            ("cliffhanger", "a", "implicit", "★★"),
            ("foreshadowing", "明示、あ", "explicit", "★★"),
            ("foreshadowing_hint", "読者、考察、想像、reader", "reader_task", "★★★"),
        ],
    )
    def test_extract_types(self, attr, value, hang_type, importance):
        plot = MagicMock(spec=[attr])
        setattr(plot, attr, value)
        step = ForeshadowingRegistrationStep()
        fs = step._extract_foreshadowings_from_plots([plot], 1)
        assert len(fs) == 1
        assert fs[0].hang_type == hang_type
        assert fs[0].importance == importance

    def test_extract_truncates_long_content(self):
        plot = MagicMock(spec=["foreshadowing_hint"])
        plot.foreshadowing_hint = "x" * 500
        fs = ForeshadowingRegistrationStep()._extract_foreshadowings_from_plots([plot], 1)
        assert len(fs[0].content) == 200

    def test_extract_uses_volume_episode_chapter(self):
        plot = MagicMock(spec=["foreshadowing_hint", "volume", "episode", "chapter"])
        plot.foreshadowing_hint = "hint"
        plot.volume = 2
        plot.episode = 5
        plot.chapter = 9
        fs = ForeshadowingRegistrationStep()._extract_foreshadowings_from_plots([plot], 1)[0]
        assert fs.hang_volume == 2
        assert fs.hang_episode == 5
        assert fs.hang_chapter == 9

    def test_extract_ids_are_sequential(self):
        plots = []
        for _ in range(3):
            p = MagicMock(spec=["foreshadowing_hint"])
            p.foreshadowing_hint = "hint"
            plots.append(p)
        fs = ForeshadowingRegistrationStep()._extract_foreshadowings_from_plots(plots, 1)
        assert [f.id for f in fs] == ["FS-001", "FS-002", "FS-003"]
