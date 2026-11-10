"""Extended coverage tests for pipeline_steps.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.pipeline_base import WorkflowContext
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


def make_ctx(**kwargs):
    base = dict(
        genre="fantasy",
        keywords="magic, sword",
        archetype_key="hero",
        target_eps=2,
        initial_limit=3,
        word_count=2000,
        book_id=1,
        start_ep=1,
        end_ep=2,
        easy_parameters={},
    )
    base.update(kwargs)
    return WorkflowContext(**base)


def make_reporter(should_stop=False):
    reporter = MagicMock()
    reporter.state.should_stop = MagicMock(return_value=should_stop)
    return reporter


def make_engine():
    """Existing test pattern for engine mock."""
    engine = MagicMock()
    engine.llm = MagicMock()
    engine.llm.generate = AsyncMock(return_value="rewritten content")
    engine.repo = MagicMock()
    engine.repo.get_book = AsyncMock(return_value=MagicMock(title="Book Title"))
    engine.repo.bible = MagicMock()
    engine.repo.bible.get_by_book_id = AsyncMock(return_value=MagicMock())
    engine.repo.episode = MagicMock()
    engine.repo.plot = MagicMock()
    engine.repo.plot.get_all_plots = AsyncMock(return_value=[])
    engine.repo.episode.get_all_by_book_id = AsyncMock(return_value=[])
    # planner setup (needed by PlanStep/CatharsisAnalysisStep)
    engine.planner = MagicMock()
    engine.planner.create_hegemony_plan = AsyncMock(
        return_value=(7, MagicMock(title="T", model_dump=MagicMock(return_value={})))
    )
    engine.planner.plan_auditor = MagicMock()
    engine.planner.plan_auditor.audit_bible_completeness = AsyncMock(return_value=True)
    return engine


# ============================================================================
# _emit_skip helper
# ============================================================================


def test_emit_skip_propagates_to_reporter_ctx_and_metrics():
    ctx = make_ctx()
    reporter = make_reporter()
    _emit_skip(reporter, ctx, "illustration", "book_id is None")
    assert ctx.warnings == ["illustration: book_id is None"]
    reporter.report.assert_called_once()
    args = reporter.report.call_args[0]
    assert "⏭️ illustration: book_id is None" in args[0]
    assert args[1] == "warning"


def test_emit_skip_swallows_reporter_and_metrics_errors():
    ctx = make_ctx()
    reporter = MagicMock()
    reporter.report = MagicMock(side_effect=RuntimeError("ui down"))
    with pytest.MonkeyPatch.context() as m:
        m.setattr("src.services.pipeline_steps.metrics.increment",
                  MagicMock(side_effect=RuntimeError("metrics down")))
        _emit_skip(reporter, ctx, "step", "reason")
    assert ctx.warnings == ["step: reason"]


# ============================================================================
# PlanStep additional tests (using existing test patterns)
# ============================================================================


@pytest.mark.asyncio
async def test_plan_step_success_with_catharsis_and_multiple_plots():
    """PlanStep カタルシスあり・プロット多数の成功テスト。"""
    ctx = make_ctx(enable_catharsis_analysis=True)
    engine = make_engine()
    engine.repo.plot.get_all_plots = AsyncMock(
        return_value=[MagicMock(tension=80), MagicMock(tension=30), MagicMock(tension=50)]
    )
    reporter = make_reporter()

    with pytest.MonkeyPatch.context() as m:
        analyzer = MagicMock()
        analyzer.analyze = MagicMock(return_value=make_wave_pattern(catharsis_indices=[1]))
        m.setattr("src.backend.engine_narrative.WavePatternAnalyzer", lambda **kw: analyzer)
        assert await PlanStep().execute(ctx, engine, reporter) is True

    assert ctx.book_id == 7
    assert ctx.easy_parameters["target_eps"] == 2
    assert "catharsis_pattern" in ctx.easy_parameters


@pytest.mark.asyncio
async def test_plan_step_with_stop_signal_and_catharsis():
    """PlanStep ストップシグナルとカタルシス分析の組み合わせテスト。"""
    ctx = make_ctx(enable_catharsis_analysis=True)
    engine = make_engine()
    reporter = make_reporter(should_stop=True)

    assert await PlanStep().execute(ctx, engine, reporter) is False
    assert ctx.warnings[-1] == "catharsis: operation halted"


def make_wave_pattern(**overrides):
    """NarrativeWavePattern 相当のモック (model_dump 付き)。"""
    pattern = MagicMock()
    dump = {"stress_levels": [80, 30], "catharsis_indices": [], "emotional_peaks": [],
            "trough_markers": [], "wave_score": 47.1, "is_healthy": True, "issues": []}
    dump.update(overrides)
    pattern.model_dump = MagicMock(return_value=dump)
    pattern.catharsis_points = []
    pattern.catharsis_indices = dump["catharsis_indices"]
    pattern.pattern_type = dump.get("pattern_type", "wave")
    pattern.amplitude = dump.get("amplitude", 12.5)
    return pattern


# ============================================================================
# WriteStep additional tests
# ============================================================================


@pytest.mark.asyncio
async def test_write_step_with_retry_exception():
    """WriteStep リトライ例外処理テスト。"""
    ctx = make_ctx()
    engine = make_engine()
    reporter = make_reporter()

    with pytest.MonkeyPatch.context() as m:
        m.setattr("src.backend.workflows._shared_ops.execute_with_retry",
                  AsyncMock(side_effect=RuntimeError("transient error")))
        with pytest.raises(RuntimeError, match="transient error"):
            await WriteStep().execute(ctx, engine, reporter)


@pytest.mark.asyncio
async def test_write_step_with_empty_content():
    """WriteStep empty content ハンドリングテスト。"""
    ctx = make_ctx(word_count=0)
    engine = make_engine()
    reporter = make_reporter()

    with pytest.MonkeyPatch.context() as m:
        retry = AsyncMock(return_value=(0, []))
        m.setattr("src.backend.workflows._shared_ops.execute_with_retry", retry)
        result = await WriteStep().execute(ctx, engine, reporter)
        assert result is True


# ============================================================================
# CatharsisAnalysisStep additional tests
# ============================================================================


@pytest.mark.asyncio
async def test_catharsis_step_with_custom_pattern():
    """CatharsisAnalysisStep カスタムパターンテスト。"""
    ctx = make_ctx()
    engine = make_engine()
    engine.repo.plot.get_all_plots = AsyncMock(
        return_value=[MagicMock(tension=70), MagicMock(tension=90), MagicMock(tension=10)]
    )
    reporter = make_reporter()

    with pytest.MonkeyPatch.context() as m:
        analyzer = MagicMock()
        analyzer.analyze = MagicMock(return_value=make_wave_pattern(catharsis_indices=[0, 2]))
        m.setattr("src.backend.engine_narrative.WavePatternAnalyzer", lambda **kw: analyzer)
        assert await CatharsisAnalysisStep().execute(ctx, engine, reporter) is True

    assert ctx.easy_parameters["catharsis_pattern"] == ctx.catharsis_pattern


@pytest.mark.asyncio
async def test_catharsis_step_with_no_plots_and_error():
    """CatharsisAnalysisStep プロットなしエラーケーステスト。"""
    ctx = make_ctx()
    engine = make_engine()
    engine.repo.plot.get_all_plots = AsyncMock(return_value=[])
    reporter = make_reporter()

    assert await CatharsisAnalysisStep().execute(ctx, engine, reporter) is True
    assert any("プロットが見つかりません" in c.args[0] for c in reporter.report.call_args_list)


# ============================================================================
# AuditRewriteStep additional tests
# ============================================================================


def make_episode(content="本文"):
    ep = MagicMock()
    ep.content = content
    return ep


@pytest.mark.asyncio
async def test_audit_rewrite_with_empty_content_skips_audit():
    """AuditRewriteStep empty content はオーディットをスキップする。"""
    ctx = make_ctx()
    engine = make_engine()
    engine.repo.episode.get_by_book_and_number = AsyncMock(return_value=make_episode(""))
    engine.repo.plot.get_by_book_and_number = AsyncMock(return_value=MagicMock())
    reporter = make_reporter()

    with pytest.MonkeyPatch.context() as m:
        adapter = MagicMock()
        adapter.audit_episode = AsyncMock(return_value={"score": 90.0})
        m.setattr("src.services.pipeline_steps.create_audit_adapter", lambda engine: adapter)
        m.setattr("src.services.pipeline_steps.create_spice_guard_adapter", lambda genre: MagicMock())
        assert await AuditRewriteStep().execute(ctx, engine, reporter) is True
    adapter.audit_episode.assert_not_called()


@pytest.mark.asyncio
async def test_audit_rewrite_with_max_iterations_exceeded():
    """AuditRewriteStep 最大イテレーション超過テスト。"""
    ctx = make_ctx(max_rewrite_iterations=1)
    engine = make_engine()
    engine.repo.episode.get_by_book_and_number = AsyncMock(return_value=make_episode())
    engine.repo.episode.update_content = AsyncMock()
    engine.repo.plot.get_by_book_and_number = AsyncMock(return_value=MagicMock())
    reporter = make_reporter()

    with pytest.MonkeyPatch.context() as m:
        adapter = MagicMock()
        adapter.audit_episode = AsyncMock(return_value={"score": 10.0, "improvements": ["fix"]})
        m.setattr("src.services.pipeline_steps.create_audit_adapter", lambda engine: adapter)
        spice = MagicMock()
        spice.extract_spice = MagicMock(return_value=[])
        spice.build_rewrite_prompt = MagicMock(return_value="prompt")
        spice.clean_markers = MagicMock(side_effect=lambda text: text)
        m.setattr("src.services.pipeline_steps.create_spice_guard_adapter",
                  lambda genre: spice)
        result = await AuditRewriteStep().execute(ctx, engine, reporter)
        assert result is True

    detail = ctx.episodes_detail[0]
    assert detail["rewrite_count"] >= 1
    assert detail["needs_human_review"] is True


# ============================================================================
# PackageStep additional tests
# ============================================================================


@pytest.mark.asyncio
async def test_package_step_with_book():
    """PackageStep ブック情報ありテスト。"""
    ctx = make_ctx(book_id=1)
    engine = make_engine()
    engine.repo.get_book = AsyncMock(return_value=MagicMock(title="Test Book", synopsis="Test synopsis"))
    reporter = make_reporter()

    assert await PackageStep().execute(ctx, engine, reporter) is True
    assert ctx.title == "Test Book"


@pytest.mark.asyncio
async def test_package_step_with_marketing_pack():
    """PackageStep マーケティングパックありテスト。"""
    ctx = make_ctx(marketing_pack={"title": "Custom Title", "synopsis": {"hook": "Hook"}})
    engine = make_engine()
    reporter = make_reporter()

    assert await PackageStep().execute(ctx, engine, reporter) is True
    assert ctx.marketing_pack == {"title": "Custom Title", "synopsis": {"hook": "Hook"}}


# ============================================================================
# IllustrationStep additional tests
# ============================================================================


@pytest.mark.asyncio
async def test_illustration_step_with_illustration_settings():
    """IllustrationStep illustration_settings 指定テスト。"""
    ctx = make_ctx(enable_illustration=True,
                   illustration_settings={"enableIllustration": True, "someSetting": True})
    engine = make_engine()
    reporter = make_reporter()

    with pytest.MonkeyPatch.context() as m:
        from src.backend.workflows.illustration_workflow import IllustrationWorkflow
        instance = MagicMock()
        instance.execute = AsyncMock(return_value={"status": "success", "illustrations": []})
        m.setattr("src.backend.workflows.illustration_workflow.IllustrationWorkflow", lambda **kwargs: instance)
        assert await IllustrationStep().execute(ctx, engine, reporter) is True


# ============================================================================
# MarketingStep additional tests
# ============================================================================


@pytest.mark.asyncio
async def test_marketing_step_with_genre_and_archetype():
    """MarketingStep ジャンルとアーキタイプありテスト。"""
    ctx = make_ctx(genre="sf", archetype_key="hero")
    engine = make_engine()
    reporter = make_reporter()

    with pytest.MonkeyPatch.context() as m:
        m.setattr("src.services.pipeline_steps.load_preset_for_pipeline",
                  lambda genre, archetype: {
                      "titles": {"title_templates": ["SF Title"]},
                      "marketing": {"synopsis_structure": {"hook": "SF Hook"},
                                    "catchphrase_templates": ["SF Catchphrase"],
                                    "tags": ["sf1", "sf2"]},
                  })
        assert await MarketingStep().execute(ctx, engine, reporter) is True

    assert ctx.title == "SF Title"
    assert ctx.easy_parameters["catchphrase"] == "SF Catchphrase"


@pytest.mark.asyncio
async def test_marketing_step_with_existing_title_and_llm():
    """MarketingStep 既存タイトルありLLMフォールバックテスト。"""
    ctx = make_ctx(title="Existing Title")
    engine = make_engine()
    reporter = make_reporter()

    with pytest.MonkeyPatch.context() as m:
        m.setattr("src.services.pipeline_steps.load_preset_for_pipeline",
                  lambda genre, archetype: {})
        assert await MarketingStep().execute(ctx, engine, reporter) is True
    assert ctx.title == "Existing Title"
    engine.llm.generate.assert_not_called()


# ============================================================================
# HookGenerationStep additional tests
# ============================================================================


def test_hook_generation_step_basic():
    """HookGenerationStep ベーシックテスト。"""
    from src.services.pipeline_steps import HookGenerationStep
    ctx = make_ctx()
    engine = make_engine()
    reporter = make_reporter()
    assert HookGenerationStep().execute(ctx, engine, reporter) is True


# ============================================================================
# ForeshadowingRegistrationStep additional tests
# ============================================================================


def make_plot(hint=None, volume=1, episode=1, chapter=1):
    plot = MagicMock(spec=["foreshadowing_hint", "volume", "episode", "chapter"])
    plot.foreshadowing_hint = hint
    plot.volume = volume
    plot.episode = episode
    plot.chapter = chapter
    return plot


@pytest.mark.asyncio
async def test_foreshadowing_step_with_explicit_and_reader_tasks():
    """ForeshadowingRegistrationStep 明示的・読者課題の両方テスト。"""
    ctx = make_ctx()
    engine = make_engine()
    repo = MagicMock()
    engine.foreshadowing_repository = repo
    engine.repo.plot.get_all_plots = AsyncMock(
        return_value=[make_plot("明示的な伏線です。", 1, 2, 3), make_plot("考察を委ねる謎。", 1, 2, 4)]
    )
    reporter = make_reporter()
    result = await ForeshadowingRegistrationStep().execute(ctx, engine, reporter)
    assert result is True
    # 2件登録されたことを確認
    assert repo.add.call_count == 2
    # 1件目は explicit、2件目は reader_task
    call1 = repo.add.call_args_list[0][0][0]
    call2 = repo.add.call_args_list[1][0][0]
    assert call1.hang_type == "explicit"
    assert call2.hang_type == "reader_task"


# ============================================================================
# IllustrationPointGenerationStep additional tests
# ============================================================================


@pytest.mark.asyncio
async def test_illustration_point_step_with_episodes():
    """IllustrationPointGenerationStep エピソードありテスト。"""
    ctx = make_ctx(enable_illustration=True)
    engine = make_engine()
    char1 = MagicMock()
    char1.name = "主人公"
    char2 = MagicMock()
    char2.name = "ヒロイン"
    engine.repo.bible.get_by_book_id = AsyncMock(
        return_value=MagicMock(characters=[char1, char2])
    )
    engine.repo.plot.get_all_plots = AsyncMock(return_value=[])
    engine.repo.episode.get_all_by_book_id = AsyncMock(
        return_value=[MagicMock() for _ in range(5)]
    )
    reporter = make_reporter()

    assert await IllustrationPointGenerationStep().execute(ctx, engine, reporter) is True
    assert len(ctx.illustration_points) > 0


# ============================================================================
# SpiceGuardAdapter integration test
# ============================================================================


def test_spice_guard_adapter_full_integration():
    """SpiceGuardAdapter フル統合テスト。"""
    from src.services.pipeline_steps import create_spice_guard_adapter

    adapter = create_spice_guard_adapter("fantasy")

    # extract_spice
    text = "主人公が酒場で飲みすぎた。暴力的な描写がある。"
    elements = adapter.extract_spice(text)
    assert isinstance(elements, list)

    # inject_markers
    markers_text = adapter.inject_markers("本文", elements)
    assert isinstance(markers_text, str)

    # clean_markers
    cleaned = adapter.clean_markers(markers_text)
    assert isinstance(cleaned, str)

    # build_rewrite_prompt
    prompt = adapter.build_rewrite_prompt("内容", ["改善"], elements)
    assert isinstance(prompt, str)
