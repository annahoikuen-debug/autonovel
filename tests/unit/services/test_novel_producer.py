"""src/services/novel_producer.py (NovelProducer) の単体テスト."""

from __future__ import annotations

from typing import Any

import pytest

from src.models.production_config import EpisodeResult, NovelProject, ProductionProgress
from src.services.novel_producer import NovelProducer


class _StubEpisodeWriter:
    """EpisodeWriter のスタブ（モックではなく単純実装）。"""

    def __init__(self, return_value: dict[str, Any] | None = None, should_fail: bool = False):
        self._return_value = return_value or {
            "text": "生成された本文です。",
            "quality_score": 0.8,
            "token_usage": {"input_tokens": 100, "output_tokens": 50},
        }
        self.should_fail = should_fail
        self.call_count = 0
        self.last_context: dict[str, Any] | None = None

    async def write(self, book_id: int, ep_num: int, context: dict[str, Any]) -> dict[str, Any]:
        self.call_count += 1
        self.last_context = context
        if self.should_fail:
            raise RuntimeError("writing failed")
        return dict(self._return_value)


class TestNovelProducerInit:
    """NovelProducer 初期化のテスト."""

    def test_init_without_token_tracker(self):
        producer = NovelProducer()
        assert producer.token_tracker is not None
        assert producer.episode_writer is not None
        assert producer.report_generator is not None
        assert producer.progress_callback is None
        assert producer._current_project is None
        assert producer._episodes == []
        assert producer._progress is None

    def test_init_with_token_tracker(self):
        from src.services.token_tracker import TokenTracker

        tracker = TokenTracker()
        producer = NovelProducer(token_tracker=tracker)
        assert producer.token_tracker is tracker


class TestSetProgressCallback:
    """set_progress_callback メソッドのテスト."""

    def test_set_progress_callback(self):
        producer = NovelProducer()

        def callback(progress: ProductionProgress):
            pass

        producer.set_progress_callback(callback)
        assert producer.progress_callback is callback


class TestCreateProject:
    """create_project メソッドのテスト."""

    def test_create_project(self):
        producer = NovelProducer()
        project = NovelProject(
            title="テスト小説",
            genre="fantasy",
            synopsis="あらすじ",
            target_episodes=5,
        )
        result = producer.create_project(project)

        assert result is project
        assert producer._current_project is project
        assert producer._episodes == []
        assert producer._progress is not None
        assert producer._progress.current_episode == 0
        assert producer._progress.total_episodes == 5
        assert producer._progress.status == "idle"

    def test_create_project_replaces_previous(self):
        producer = NovelProducer()
        project1 = NovelProject(title="p1", genre="g1", synopsis="s1", target_episodes=3)
        project2 = NovelProject(title="p2", genre="g2", synopsis="s2", target_episodes=7)
        producer.create_project(project1)
        producer.create_project(project2)

        assert producer._current_project is project2
        assert producer._progress.total_episodes == 7


class TestGetProgress:
    """get_progress メソッドのテスト."""

    def test_get_progress_before_create_project(self):
        producer = NovelProducer()
        assert producer.get_progress() is None

    def test_get_progress_after_create_project(self):
        producer = NovelProducer()
        project = NovelProject(title="t", genre="g", synopsis="s", target_episodes=10)
        producer.create_project(project)
        progress = producer.get_progress()
        assert progress is not None
        assert progress.total_episodes == 10
        assert progress.status == "idle"


class TestGetEpisodes:
    """get_episodes メソッドのテスト."""

    def test_get_episodes_empty(self):
        producer = NovelProducer()
        assert producer.get_episodes() == []

    def test_get_episodes_after_adding(self):
        producer = NovelProducer()
        result = EpisodeResult(
            ep_num=1,
            title="第1話",
            text="本文",
            word_count=2,
            quality_score=0.8,
            status="completed",
        )
        producer._episodes.append(result)
        episodes = producer.get_episodes()
        assert len(episodes) == 1
        assert episodes[0] is result


class TestGenerateReportNoProject:
    """generate_report のプロジェクトなしエラーケースのテスト."""

    def test_generate_report_without_project_raises(self):
        producer = NovelProducer()
        with pytest.raises(ValueError, match="プロジェクトが設定されていません"):
            producer.generate_report()


class TestUpdateProgress:
    """_update_progress メソッドのテスト."""

    def test_update_progress_without_progress(self):
        producer = NovelProducer()
        # _progress が None の場合はエラーにならない
        producer._update_progress("idle", "message")

    def test_update_progress_with_progress(self):
        producer = NovelProducer()
        producer._progress = ProductionProgress(
            current_episode=0,
            total_episodes=10,
            status="idle",
        )
        producer._update_progress("running", "生成中")
        assert producer._progress.status == "running"
        assert producer._progress.message == "生成中"


class TestBuildContext:
    """_build_context メソッドのテスト."""

    def test_build_context_first_episode(self):
        producer = NovelProducer()
        project = NovelProject(
            title="t", genre="g", synopsis="s",
            target_episodes=5, target_word_count_per_episode=3000,
        )
        producer.create_project(project)
        context = producer._build_context(ep_num=1)

        assert context["ep_num"] == 1
        assert context["is_first"] is True
        assert context["is_last"] is False
        assert context["target_word_count"] == 3000
        assert "previous_episode" not in context

    def test_build_context_last_episode(self):
        producer = NovelProducer()
        project = NovelProject(
            title="t", genre="g", synopsis="s",
            target_episodes=5, target_word_count_per_episode=3000,
        )
        producer.create_project(project)
        context = producer._build_context(ep_num=5)

        assert context["ep_num"] == 5
        assert context["is_first"] is False
        assert context["is_last"] is True

    def test_build_context_without_project(self):
        producer = NovelProducer()
        # _current_project が None の場合
        context = producer._build_context(ep_num=1)
        assert context["is_first"] is True
        assert context["is_last"] is False
        assert context["target_word_count"] == 3000  # デフォルト値

    def test_build_context_with_previous_episode(self):
        producer = NovelProducer()
        project = NovelProject(
            title="t", genre="g", synopsis="s",
            target_episodes=5, target_word_count_per_episode=3000,
        )
        producer.create_project(project)
        # 1話目を追加
        ep1 = EpisodeResult(
            ep_num=1,
            title="第1話",
            text="あ" * 500,
            word_count=500,
            quality_score=0.8,
            status="completed",
        )
        producer._episodes.append(ep1)

        context = producer._build_context(ep_num=2)
        assert context["ep_num"] == 2
        assert context["is_first"] is False
        assert context["previous_episode"] is not None
        assert context["previous_episode"]["title"] == "第1話"
        assert context["previous_episode"]["ending"] == "あ" * 200  # 最後の200文字
        assert context["previous_episode"]["summary"] == "あ" * 200  # 最初の200文字


class TestGenerateEpisode:
    """generate_episode メソッドのテスト."""

    @pytest.mark.asyncio
    async def test_generate_episode_success(self):
        producer = NovelProducer()
        writer = _StubEpisodeWriter()
        producer.episode_writer = writer

        project = NovelProject(
            title="t", genre="g", synopsis="s",
            target_episodes=3, target_word_count_per_episode=3000,
        )
        producer.create_project(project)

        result = await producer.generate_episode(project_id=1, ep_num=1)

        assert isinstance(result, EpisodeResult)
        assert result.ep_num == 1
        assert result.title == "第1話"
        assert result.text == "生成された本文です。"
        assert result.word_count == len("生成された本文です。")
        assert result.quality_score == 0.8
        assert result.token_usage == {"input_tokens": 100, "output_tokens": 50}
        assert result.status == "completed"
        assert writer.call_count == 1
        assert len(producer._episodes) == 1
        assert producer._episodes[0] is result

    @pytest.mark.asyncio
    async def test_generate_episode_records_progress(self):
        producer = NovelProducer()
        writer = _StubEpisodeWriter()
        producer.episode_writer = writer

        project = NovelProject(
            title="t", genre="g", synopsis="s",
            target_episodes=3, target_word_count_per_episode=3000,
        )
        producer.create_project(project)

        await producer.generate_episode(project_id=1, ep_num=2)

        progress = producer.get_progress()
        assert progress is not None
        assert progress.current_episode == 2
        assert 2 in progress.completed_eps
        assert progress.status == "running"

    @pytest.mark.asyncio
    async def test_generate_episode_without_project_calls_writer(self):
        # _current_project が None でも ValueError は投げられず、
        # episode_writer.write が呼ばれる（ソースコード上のチェックはコメントのみ）
        producer = NovelProducer()
        writer = _StubEpisodeWriter()
        producer.episode_writer = writer

        result = await producer.generate_episode(project_id=1, ep_num=1)

        assert isinstance(result, EpisodeResult)
        assert writer.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_episode_writer_failure_propagates(self):
        producer = NovelProducer()
        writer = _StubEpisodeWriter(should_fail=True)
        producer.episode_writer = writer

        project = NovelProject(
            title="t", genre="g", synopsis="s",
            target_episodes=3, target_word_count_per_episode=3000,
        )
        producer.create_project(project)

        with pytest.raises(RuntimeError, match="writing failed"):
            await producer.generate_episode(project_id=1, ep_num=1)

        # 失敗してもエピソードは追加されない（例外前に append されていない）
        assert len(producer._episodes) == 0


class TestGenerateAllEpisodes:
    """generate_all_episodes メソッドのテスト."""

    @pytest.mark.asyncio
    async def test_generate_all_episodes_success(self):
        producer = NovelProducer()
        writer = _StubEpisodeWriter()
        producer.episode_writer = writer

        project = NovelProject(
            title="t", genre="g", synopsis="s",
            target_episodes=3, target_word_count_per_episode=3000,
        )
        producer.create_project(project)

        results = await producer.generate_all_episodes(project_id=1)

        assert len(results) == 3
        assert writer.call_count == 3
        assert all(isinstance(r, EpisodeResult) for r in results)
        assert [r.ep_num for r in results] == [1, 2, 3]

        progress = producer.get_progress()
        assert progress is not None
        assert progress.status == "completed"
        assert progress.is_complete is True

    @pytest.mark.asyncio
    async def test_generate_all_episodes_without_project_raises(self):
        producer = NovelProducer()
        producer.episode_writer = _StubEpisodeWriter()
        with pytest.raises(ValueError, match="プロジェクトが設定されていません"):
            await producer.generate_all_episodes(project_id=1)

    @pytest.mark.asyncio
    async def test_generate_all_episodes_partial_failure(self):
        producer = NovelProducer()
        # 2話目で失敗するスタブ
        call_count = {"n": 0}

        async def flaky_write(book_id, ep_num, context):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("episode 2 failed")
            return {
                "text": f"text {ep_num}",
                "quality_score": 0.8,
                "token_usage": {"input_tokens": 10, "output_tokens": 10},
            }

        writer = _StubEpisodeWriter()
        writer.write = flaky_write  # type: ignore[method-assign]
        producer.episode_writer = writer

        project = NovelProject(
            title="t", genre="g", synopsis="s",
            target_episodes=3, target_word_count_per_episode=3000,
        )
        producer.create_project(project)

        with pytest.raises(RuntimeError, match="episode 2 failed"):
            await producer.generate_all_episodes(project_id=1)

        # 失敗時点で 1話目のみ記録されている
        assert len(producer._episodes) == 1
        assert producer._episodes[0].ep_num == 1

        progress = producer.get_progress()
        assert progress is not None
        assert progress.status == "failed"


class TestGenerateReport:
    """generate_report メソッドのテスト."""

    def test_generate_report_success(self):
        producer = NovelProducer()
        writer = _StubEpisodeWriter()
        producer.episode_writer = writer

        project = NovelProject(
            title="テスト小説",
            genre="fantasy",
            synopsis="あらすじ",
            target_episodes=2,
            target_word_count_per_episode=3000,
        )
        producer.create_project(project)

        # 同期的にエピソードを追加（generate_episode は async なので直接 _episodes に追加）
        ep1 = EpisodeResult(
            ep_num=1,
            title="第1話",
            text="第1話の本文です。",
            word_count=10,
            quality_score=0.8,
            token_usage={"input_tokens": 100, "output_tokens": 50},
            status="completed",
        )
        ep2 = EpisodeResult(
            ep_num=2,
            title="第2話",
            text="第2話の本文です。",
            word_count=10,
            quality_score=0.9,
            token_usage={"input_tokens": 200, "output_tokens": 100},
            status="completed",
        )
        producer._episodes = [ep1, ep2]

        report = producer.generate_report()

        assert report is not None
        assert report.title == "テスト小説"
        assert report.genre == "fantasy"
        assert len(report.episode_summaries) == 2
        assert report.episode_summaries[0].ep_num == 1
        assert report.episode_summaries[0].title == "第1話"
        assert report.episode_summaries[0].word_count == len("第1話の本文です。")
        assert report.episode_summaries[0].quality_score == 0.8
        assert report.episode_summaries[1].ep_num == 2
        assert report.episode_summaries[1].word_count == len("第2話の本文です。")
        assert report.episode_summaries[1].quality_score == 0.9
        # トークントラッカーに何も追加していないので 0
        assert report.token_usage.total_tokens == 0
        assert report.token_usage.episode_count == 0

    def test_generate_report_without_episodes(self):
        producer = NovelProducer()
        project = NovelProject(
            title="t", genre="g", synopsis="s",
            target_episodes=1,
        )
        producer.create_project(project)
        # エピソードなし

        report = producer.generate_report()

        assert report.episode_summaries == []
        assert report.token_usage.total_tokens == 0
        assert report.token_usage.episode_count == 0


class TestGenerateAllEpisodesEdgeCases:
    """generate_all_episodes のエッジケーステスト."""

    @pytest.mark.asyncio
    async def test_generate_all_episodes_empty_token_usage(self):
        # token_usage が空 dict の場合のパスをカバー
        producer = NovelProducer()

        async def empty_token_write(book_id, ep_num, context):
            return {
                "text": f"text {ep_num}",
                "quality_score": 0.8,
                "token_usage": {},  # 空
            }

        writer = _StubEpisodeWriter()
        writer.write = empty_token_write  # type: ignore[method-assign]
        producer.episode_writer = writer

        project = NovelProject(
            title="t", genre="g", synopsis="s",
            target_episodes=2, target_word_count_per_episode=3000,
        )
        producer.create_project(project)

        results = await producer.generate_all_episodes(project_id=1)

        assert len(results) == 2
        # token_usage が空でもエラーにならない
        progress = producer.get_progress()
        assert progress is not None
        assert progress.status == "completed"


class TestGenerateEpisodeEdgeCases:
    """generate_episode のエッジケーステスト."""

    @pytest.mark.asyncio
    async def test_generate_episode_without_progress(self):
        # _progress が None の場合（create_project を呼ばない）
        producer = NovelProducer()
        writer = _StubEpisodeWriter()
        producer.episode_writer = writer

        # _current_project も None だが、generate_episode はチェックを通過して writer.write を呼ぶ
        result = await producer.generate_episode(project_id=1, ep_num=1)

        assert isinstance(result, EpisodeResult)
        assert writer.call_count == 1
        # _progress は None のまま
        assert producer.get_progress() is None
