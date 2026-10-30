"""Unit tests for WritingCoordinator."""

from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
import pytest

from src.domain.writing.coordinator import (
    ChapterImportNotAvailableError,
    WritingCoordinator,
)


class TestWritingCoordinator:
    """Tests for WritingCoordinator."""

    @pytest.fixture
    def mock_writer(self):
        writer = AsyncMock()
        writer.generate_episodes_pipeline = AsyncMock(return_value=(1000, []))
        writer.generate_episodes = AsyncMock(return_value=1000)
        writer.analyze_and_import_chapter = AsyncMock(return_value="imported")
        return writer

    @pytest.fixture
    def mock_auditor(self):
        auditor = MagicMock()
        auditor.audit_quantitative.return_value = (
            80.0,
            {"cliches": [], "dialogue_ratio": 0.3, "rhythm_score": 70.0},
        )
        return auditor

    @pytest.fixture
    def mock_pdca_runner(self):
        runner = AsyncMock()
        pdca_result = MagicMock()
        pdca_result.initial_score = 50.0
        pdca_result.final_score = 75.0
        pdca_result.converged = True
        runner.run_pdca_cycle = AsyncMock(return_value=("draft", pdca_result))
        return runner

    @pytest.fixture
    def mock_book_score_calculator(self):
        calculator = AsyncMock()
        score_obj = MagicMock()
        score_obj.overall_score = 80.0
        score_obj.structure_score = 80.0
        score_obj.coherency_score = 80.0
        score_obj.factual_grounding_score = 80.0
        score_obj.visual_textual_synergy_score = 80.0
        score_obj.reader_experience_score = 80.0
        calculator.calculate = AsyncMock(return_value=score_obj)
        return calculator

    @pytest.fixture
    def coordinator(self, mock_writer, mock_book_score_calculator, mock_auditor, mock_pdca_runner):
        return WritingCoordinator(
            writer=mock_writer,
            book_score_calculator=mock_book_score_calculator,
            score_threshold=70.0,
            auditor=mock_auditor,
            pdca_runner=mock_pdca_runner,
        )

    def test_coordinator_initialization(self, coordinator):
        """Test coordinator initializes with correct defaults."""
        assert coordinator.writer is not None
        assert coordinator.book_score_calculator is not None
        assert coordinator.score_threshold == 70.0
        assert coordinator._auditor is not None
        assert coordinator._pdca_runner is not None

    @pytest.mark.asyncio
    async def test_generate_episodes_pipeline_delegates_to_writer(self, coordinator, mock_writer):
        """Test generate_episodes_pipeline delegates to writer."""
        reporter = MagicMock()
        result = await coordinator.generate_episodes_pipeline(
            book_id=1,
            start_ep=1,
            end_ep=3,
            passion=0.8,
            target_word_count=2000,
            is_easy_mode=True,
            reporter=reporter,
        )
        assert result == (1000, [])
        mock_writer.generate_episodes_pipeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_episodes_delegates_to_writer(self, coordinator, mock_writer):
        """Test generate_episodes delegates to writer."""
        reporter = MagicMock()
        result = await coordinator.generate_episodes(
            book_id=1,
            start_ep=1,
            end_ep=1,
            passion=0.8,
            target_word_count=2000,
            is_easy_mode=True,
            reporter=reporter,
            auto_regenerate=False,
        )
        assert result == 1000
        mock_writer.generate_episodes.assert_called_once()

    def test_audit_generated_text(self, coordinator, mock_auditor):
        """Test audit_generated_text executes injected auditor port."""
        text = "「行くぞ！」アルトは叫び、剣を抜いた。夜の風が冷たく吹き抜ける。"
        result = coordinator.audit_generated_text(text)
        mock_auditor.audit_quantitative.assert_called_once_with(text)
        assert "quantitative_score" in result
        assert "is_acceptable" in result
        assert "warnings" in result
        assert isinstance(result["warnings"], list)
        assert result["quantitative_score"] > 0

    def test_audit_generated_text_raises_without_auditor(self, mock_writer, mock_book_score_calculator):
        """auditor 未注入時に audit_generated_text が RuntimeError を送出する."""
        coordinator = WritingCoordinator(
            writer=mock_writer,
            book_score_calculator=mock_book_score_calculator,
            score_threshold=70.0,
        )
        with pytest.raises(RuntimeError, match="auditor ポートが未注入"):
            coordinator.audit_generated_text("テキスト")

    @pytest.mark.asyncio
    async def test_calculate_book_score_returns_dict(self, coordinator, mock_book_score_calculator):
        """Test calculate_book_score returns expected dict structure."""
        result = await coordinator.calculate_book_score(
            book_id=1,
            chapter_number=1,
            genre="fantasy",
            phase="writing",
        )
        assert result is not None
        assert "overall_score" in result
        assert "structure_score" in result
        assert "regeneration_triggered" in result
        assert "regeneration_actions" in result
        assert result["regeneration_triggered"] is False

    @pytest.mark.asyncio
    async def test_analyze_and_import_chapter_delegates(self, coordinator, mock_writer):
        """Test analyze_and_import_chapter delegates to writer."""
        result = await coordinator.analyze_and_import_chapter(
            book_id=1,
            ep_num=1,
            import_text="手書き原稿",
            do_refine=True,
        )
        assert result == "imported"
        mock_writer.analyze_and_import_chapter.assert_called_once_with(
            book_id=1, ep_num=1, import_text="手書き原稿", do_refine=True
        )

    def test_identify_low_dimensions(self, coordinator):
        """Test _identify_low_dimensions identifies scores below 60."""
        score_obj = MagicMock()
        score_obj.structure_score = 50
        score_obj.coherency_score = 70
        score_obj.factual_grounding_score = 55
        score_obj.visual_textual_synergy_score = 80
        score_obj.reader_experience_score = 90

        low = coordinator._identify_low_dimensions(score_obj)
        assert "structure" in low
        assert "factual_grounding" in low
        assert "coherency" not in low
        assert len(low) == 2

    def test_generate_regeneration_actions(self, coordinator):
        """Test _generate_regeneration_actions creates proper action dicts."""
        actions = coordinator._generate_regeneration_actions(["structure", "coherency"])
        assert len(actions) == 2
        assert actions[0]["dimension"] == "structure"
        assert actions[1]["dimension"] == "coherency"
        assert "target_agent" in actions[0]
        assert "action" in actions[0]
        assert "params" in actions[0]

    def test_generate_regeneration_actions_unknown_dimension_skipped(self, coordinator):
        """Test _generate_regeneration_actions skips unknown dimensions."""
        actions = coordinator._generate_regeneration_actions(["unknown_dimension"])
        assert actions == []

    def test_generate_regeneration_actions_all_dimensions(self, coordinator):
        """Test _generate_regeneration_actions covers every known dimension."""
        actions = coordinator._generate_regeneration_actions(
            [
                "structure",
                "coherency",
                "factual_grounding",
                "visual_textual_synergy",
                "reader_experience",
            ]
        )
        assert len(actions) == 5
        assert {a["dimension"] for a in actions} == {
            "structure",
            "coherency",
            "factual_grounding",
            "visual_textual_synergy",
            "reader_experience",
        }

    def test_identify_low_dimensions_all_low(self, coordinator):
        """Test _identify_low_dimensions when every dimension is below threshold."""
        score_obj = MagicMock()
        for attr in (
            "structure_score",
            "coherency_score",
            "factual_grounding_score",
            "visual_textual_synergy_score",
            "reader_experience_score",
        ):
            setattr(score_obj, attr, 50.0)

        low = coordinator._identify_low_dimensions(score_obj)
        assert len(low) == 5

    def test_audit_generated_text_warnings(self, coordinator, mock_auditor):
        """Test audit_generated_text emits cliche/dialogue/rhythm warnings."""
        mock_auditor.audit_quantitative.return_value = (
            50.0,
            {
                "cliches": ["定型表現A", "定型表現B", "定型表現C"],
                "dialogue_ratio": 0.05,
                "rhythm_score": 40.0,
            },
        )
        result = coordinator.audit_generated_text("テキスト")

        assert result["is_acceptable"] is False
        assert len(result["warnings"]) == 3
        assert any("AI定型表現" in w for w in result["warnings"])
        assert any("会話文比率が低すぎます" in w for w in result["warnings"])
        assert any("文長リズムに偏りがあります" in w for w in result["warnings"])

    def test_audit_generated_text_dialogue_ratio_too_high(self, coordinator, mock_auditor):
        """Test audit_generated_text warns when dialogue ratio is too high."""
        mock_auditor.audit_quantitative.return_value = (
            80.0,
            {"cliches": [], "dialogue_ratio": 0.8, "rhythm_score": 70.0},
        )
        result = coordinator.audit_generated_text("テキスト")
        assert any("会話文比率が高すぎます" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_calculate_book_score_no_calculator(self, mock_writer):
        """calculate_book_score returns None when book_score_calculator is not injected."""
        coordinator = WritingCoordinator(writer=mock_writer, score_threshold=70.0)
        result = await coordinator.calculate_book_score(book_id=1, chapter_number=1)
        assert result is None

    @pytest.mark.asyncio
    async def test_calculate_book_score_below_threshold(self, coordinator, mock_book_score_calculator):
        """calculate_book_score marks regeneration_triggered when below threshold."""
        low_score = MagicMock()
        low_score.overall_score = 50.0
        low_score.structure_score = 50.0
        low_score.coherency_score = 50.0
        low_score.factual_grounding_score = 50.0
        low_score.visual_textual_synergy_score = 50.0
        low_score.reader_experience_score = 50.0
        mock_book_score_calculator.calculate = AsyncMock(return_value=low_score)

        result = await coordinator.calculate_book_score(book_id=1, chapter_number=1)

        assert result is not None
        assert result["regeneration_triggered"] is True
        assert "low_dimensions" in result
        assert "regeneration_actions" in result

    @pytest.mark.asyncio
    async def test_generate_episodes_pdca_disabled_local_patch(self, mock_writer):
        """generate_episodes with PDCA disabled applies local patch when repo exists."""
        coordinator = WritingCoordinator(
            writer=mock_writer,
            book_score_calculator=MagicMock(),
            score_threshold=70.0,
        )
        coordinator.pdca_controller = MagicMock()
        coordinator.pdca_controller.should_regenerate_full_text = MagicMock(return_value=False)
        coordinator.pdca_controller.can_do_local_patch = MagicMock(return_value=True)
        coordinator.pdca_controller.record_local_patch = MagicMock()
        coordinator.repo = MagicMock()
        episode = MagicMock()
        episode.content = "original text"
        coordinator.repo.get_episode_by_number = MagicMock(return_value=episode)
        issue = MagicMock()
        issue.location = (0, 10)
        issue.suggestion = "fix it"
        issue.type = "typo"
        issue.message = "typo found"
        coordinator.audit_pipeline.run = MagicMock(return_value=[issue])
        coordinator.local_polisher.polish = MagicMock(return_value="polished text")

        reporter = MagicMock()
        result = await coordinator.generate_episodes(
            book_id=1,
            start_ep=1,
            end_ep=1,
            passion=0.8,
            target_word_count=2000,
            is_easy_mode=True,
            reporter=reporter,
            auto_regenerate=True,
        )

        assert result == 1000
        reporter.report.assert_any_call(
            "Ep.1-1: PDCAポリシーにより全文再生成ループは無効化されています",
            "info",
        )
        coordinator.local_polisher.polish.assert_called_once()
        coordinator.repo.save_episode.assert_called_once_with(episode)
        coordinator.pdca_controller.record_local_patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_episodes_regeneration_loop(
        self, coordinator, mock_writer, mock_pdca_runner, mock_book_score_calculator
    ):
        """generate_episodes runs the PDCA regeneration loop when score is below threshold."""
        reporter = MagicMock()
        coordinator.pdca_controller.should_regenerate_full_text = MagicMock(return_value=True)
        low_score = MagicMock()
        low_score.overall_score = 50.0
        low_score.structure_score = 50.0
        low_score.coherency_score = 50.0
        low_score.factual_grounding_score = 50.0
        low_score.visual_textual_synergy_score = 50.0
        low_score.reader_experience_score = 50.0
        mock_book_score_calculator.calculate = AsyncMock(return_value=low_score)

        result = await coordinator.generate_episodes(
            book_id=1,
            start_ep=1,
            end_ep=1,
            passion=0.8,
            target_word_count=2000,
            is_easy_mode=True,
            reporter=reporter,
            auto_regenerate=True,
            max_retries=2,
        )

        assert result == 1000
        mock_pdca_runner.run_pdca_cycle.assert_called()
        reporter.report.assert_any_call("Ep.1: 最大リトライ(2)到達、スコア 50.0 で終了", "error")

    @pytest.mark.asyncio
    async def test_trigger_pdca_rewrite_skips_when_runner_not_injected(
        self, mock_writer, mock_book_score_calculator, mock_auditor
    ):
        """_trigger_pdca_rewrite reports error and returns when pdca_runner is None."""
        coordinator = WritingCoordinator(
            writer=mock_writer,
            book_score_calculator=mock_book_score_calculator,
            auditor=mock_auditor,
            score_threshold=70.0,
            # pdca_runner intentionally None
        )
        reporter = MagicMock()
        await coordinator._trigger_pdca_rewrite(
            book_id=1, ep_num=1, low_dimensions=["structure"], actions=[], reporter=reporter
        )
        reporter.report.assert_any_call("Ep.1: pdca_runner ポートが未注入のため再執筆をスキップ", "error")

    def test_supports_chapter_import_no_method(self, coordinator):
        """supports_chapter_import returns False when writer lacks the method."""
        coordinator.writer = SimpleNamespace()
        assert coordinator.supports_chapter_import() is False

    def test_supports_chapter_import_unimplemented_marker(self, coordinator):
        """supports_chapter_import returns False when method is marked unimplemented."""
        method = MagicMock()
        method._unimplemented_marker = True
        coordinator.writer.analyze_and_import_chapter = method
        assert coordinator.supports_chapter_import() is False

    def test_supports_chapter_import_available(self, coordinator):
        """supports_chapter_import returns True for a real implementation."""

        async def real_method(*args, **kwargs):
            return "ok"

        coordinator.writer.analyze_and_import_chapter = real_method
        assert coordinator.supports_chapter_import() is True

    @pytest.mark.asyncio
    async def test_analyze_and_import_chapter_not_available(self, coordinator):
        """analyze_and_import_chapter raises ChapterImportNotAvailableError when unsupported."""
        coordinator.writer = SimpleNamespace()
        with pytest.raises(ChapterImportNotAvailableError):
            await coordinator.analyze_and_import_chapter(book_id=1, ep_num=1, import_text="手書き原稿", do_refine=True)

    @pytest.mark.asyncio
    async def test_apply_single_shot_polish_no_repo(self, coordinator):
        """_apply_single_shot_polish returns immediately when repo is None."""
        coordinator.repo = None
        await coordinator._apply_single_shot_polish(book_id=1, ep_num=1)

    @pytest.mark.asyncio
    async def test_apply_single_shot_polish_no_episode(self, coordinator):
        """_apply_single_shot_polish returns when episode is not found."""
        coordinator.repo = MagicMock()
        coordinator.repo.get_episode_by_number = MagicMock(return_value=None)
        await coordinator._apply_single_shot_polish(book_id=1, ep_num=1)

    @pytest.mark.asyncio
    async def test_apply_single_shot_polish_no_issues(self, coordinator):
        """_apply_single_shot_polish returns when audit finds no issues."""
        episode = MagicMock(content="text")
        coordinator.repo = MagicMock()
        coordinator.repo.get_episode_by_number = MagicMock(return_value=episode)
        coordinator.audit_pipeline.run = MagicMock(return_value=[])
        await coordinator._apply_single_shot_polish(book_id=1, ep_num=1)

    @pytest.mark.asyncio
    async def test_apply_single_shot_polish_no_candidate(self, coordinator):
        """_apply_single_shot_polish returns when no patch candidate exists."""
        episode = MagicMock(content="text")
        coordinator.repo = MagicMock()
        coordinator.repo.get_episode_by_number = MagicMock(return_value=episode)
        issue = MagicMock()
        issue.location = None
        issue.suggestion = None
        coordinator.audit_pipeline.run = MagicMock(return_value=[issue])
        await coordinator._apply_single_shot_polish(book_id=1, ep_num=1)
