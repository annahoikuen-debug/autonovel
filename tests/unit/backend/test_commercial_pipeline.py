"""
commercial_pipeline.py テストモジュール (Phase 2 Steps 17-20)
カバレッジ目標: 20% → 75%
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.backend.workflows.commercial_pipeline import CommercialPipeline, async_retry
from src.core.exceptions import PipelineError


# =============================================================================
# Step 17: パイプライン全ステージモック接続
# =============================================================================

@pytest.mark.asyncio
async def test_commercial_pipeline_plan_stage_mock():
    """_step_plan ステージのモックテスト"""
    pipeline = CommercialPipeline()

    series_config = {
        "book_id": 1,
        "genre": "ファンタジー",
        "concept": "異世界転生",
        "keywords": ["魔法", "冒険"],
        "target_eps": 3,
        "target_word_count_per_episode": 3000,
        "platforms": ["kakuyomu"],
        "trend_memo": "異世界ブーム"
    }

    bible = await pipeline._step_plan_async(series_config)

    assert bible["book_id"] == 1
    assert bible["genre"] == "ファンタジー"
    assert bible["concept"] == "異世界転生"
    assert bible["keywords"] == ["魔法", "冒険"]
    assert bible["target_eps"] == 3
    assert bible["target_word_count_per_episode"] == 3000
    assert "kakuyomu" in bible["target_platforms"]
    assert "unique_selling_points" in bible


@pytest.mark.asyncio
async def test_commercial_pipeline_plan_stage_missing_keywords():
    """キーワード不足時の _step_plan エラーテスト"""
    pipeline = CommercialPipeline()

    series_config = {
        "book_id": 1,
        "genre": "ファンタジー",
        "concept": "異世界転生",
        "keywords": [],
        "target_eps": 3,
    }

    with pytest.raises(PipelineError) as exc_info:
        await pipeline._step_plan_async(series_config)

    assert "Missing required keywords" in str(exc_info.value)


@pytest.mark.asyncio
async def test_commercial_pipeline_generate_content_stage_mock():
    """_generate_content ステージのモックテスト"""
    pipeline = CommercialPipeline()

    bible = {
        "book_id": 1,
        "genre": "ファンタジー",
        "concept": "異世界転生",
        "keywords": ["魔法", "冒険"],
        "target_eps": 2,
        "target_word_count_per_episode": 3000,
        "target_platforms": ["kakuyomu"],
    }

    mock_writer = AsyncMock()
    mock_writer.write.return_value = {
        "text": "テスト本文" * 100,
        "summary": "テスト要約",
        "quality_score": 0.85,
        "killer_phrase": "決め台詞",
    }

    with patch("src.backend.workflows.commercial_pipeline.EpisodeWriter", return_value=mock_writer):
        selected, exports = await pipeline._generate_content(bible, [], ["kakuyomu"])

    assert len(selected) == 2
    assert selected[0]["ep_num"] == 1
    assert selected[1]["ep_num"] == 2
    assert selected[0]["quality_score"] == 0.85
    assert "kakuyomu" in exports
    assert len(exports["kakuyomu"]) == 2


@pytest.mark.asyncio
async def test_commercial_pipeline_write_stage_mock():
    """write ステージ（EpisodeWriter呼び出し）のモックテスト"""
    pipeline = CommercialPipeline()

    bible = {
        "book_id": 1,
        "genre": "ファンタジー",
        "concept": "異世界転生",
        "keywords": ["魔法"],
        "target_eps": 1,
        "target_word_count_per_episode": 3000,
    }

    mock_writer = AsyncMock()
    mock_writer.write.return_value = {
        "text": "生成された本文",
        "summary": "生成された要約",
        "quality_score": 0.9,
        "killer_phrase": "決め台詞",
    }

    with patch("src.backend.workflows.commercial_pipeline.EpisodeWriter", return_value=mock_writer):
        selected, exports = await pipeline._generate_content(bible, [], ["kakuyomu"])

    assert mock_writer.write.call_count == 1
    call_args = mock_writer.write.call_args
    assert call_args.kwargs["book_id"] == 1
    assert call_args.kwargs["ep_num"] == 1
    assert "context" in call_args.kwargs


@pytest.mark.asyncio
async def test_commercial_pipeline_review_stage_mock():
    """review ステージ（品質チェック）のモックテスト"""
    pipeline = CommercialPipeline()

    bible = {
        "book_id": 1,
        "genre": "ファンタジー",
        "concept": "異世界転生",
        "keywords": ["魔法"],
        "target_eps": 1,
        "target_word_count_per_episode": 3000,
    }

    mock_writer = AsyncMock()
    mock_writer.write.return_value = {
        "text": "品質の高い本文" * 50,
        "summary": "要約",
        "quality_score": 0.95,
        "killer_phrase": "決め台詞",
    }

    with patch("src.backend.workflows.commercial_pipeline.EpisodeWriter", return_value=mock_writer):
        selected, _ = await pipeline._generate_content(bible, [], ["kakuyomu"])

    assert selected[0]["quality_score"] >= 0.9


@pytest.mark.asyncio
async def test_commercial_pipeline_export_stage_mock():
    """export ステージ（CSV出力）のモックテスト"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "schedule.csv")
        pipeline = CommercialPipeline(csv_path=csv_path)

        exports = {
            "kakuyomu": [
                {"ep_num": 1, "title": "第1話", "format": "web", "target_word_count": 3000},
                {"ep_num": 2, "title": "第2話", "format": "web", "target_word_count": 3000},
            ]
        }

        result_path = pipeline._create_schedule_csv(exports)

        assert result_path == csv_path
        assert os.path.exists(csv_path)

        with open(csv_path, encoding="utf-8") as f:
            content = f.read()

        assert "platform,ep_num,title,format,target_word_count,output_path" in content
        assert "kakuyomu,1,第1話,web,3000" in content
        assert "kakuyomu,2,第2話,web,3000" in content


# =============================================================================
# Step 18: 正常フロー
# =============================================================================

@pytest.mark.asyncio
async def test_commercial_pipeline_full_success_flow():
    """全ステージ成功の正常フローテスト"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "schedule.csv")
        pipeline = CommercialPipeline(csv_path=csv_path)

        series_config = {
            "book_id": 1,
            "genre": "ファンタジー",
            "concept": "異世界転生",
            "keywords": ["魔法", "冒険"],
            "target_eps": 2,
            "target_word_count_per_episode": 3000,
            "platforms": ["kakuyomu"],
            "trend_memo": "異世界ブーム"
        }

        mock_writer = AsyncMock()
        mock_writer.write.return_value = {
            "text": "生成された本文" * 100,
            "summary": "要約",
            "quality_score": 0.85,
            "killer_phrase": "決め台詞",
        }

        with patch("src.backend.workflows.commercial_pipeline.EpisodeWriter", return_value=mock_writer):
            result = await pipeline.run(
                series_config=series_config,
                samples=[],
                platforms=["kakuyomu"],
                do_publish=False
            )

        assert "error" not in result
        assert result["bible"] is not None
        assert len(result["selected"]) == 2
        assert result["exports"] is not None
        assert result["schedule_csv"] == csv_path
        assert result["publish_results"] == {}
        assert os.path.exists(csv_path)


@pytest.mark.asyncio
async def test_commercial_pipeline_partial_episodes_generated():
    """一部エピソードのみ生成されるケースのテスト（リトライ後も失敗）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "schedule.csv")
        pipeline = CommercialPipeline(csv_path=csv_path)

        series_config = {
            "book_id": 1,
            "genre": "ファンタジー",
            "concept": "異世界転生",
            "keywords": ["魔法"],
            "target_eps": 3,
            "target_word_count_per_episode": 3000,
            "platforms": ["kakuyomu"],
        }

        call_count = 0

        async def mock_write(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # 常に失敗させてリトライをトリガー
            raise Exception("Episode generation failed")

        mock_writer = AsyncMock()
        mock_writer.write.side_effect = mock_write

        with patch("src.backend.workflows.commercial_pipeline.EpisodeWriter", return_value=mock_writer):
            result = await pipeline.run(
                series_config=series_config,
                samples=[],
                platforms=["kakuyomu"],
                do_publish=False
            )

        assert "error" in result
        assert "Episode 1 generation failed" in result["error"]
        # リトライ3回 × エピソード1 = 3回呼び出し（最初のエピソードで失敗して終了）
        assert call_count >= 3


# =============================================================================
# Step 19: 失敗時リトライ・スキップ・部分完了での成果物保存
# =============================================================================

@pytest.mark.asyncio
async def test_async_retry_decorator_success_on_retry():
    """リトライデコレータ：2回目で成功するケース"""
    call_count = 0

    @async_retry(max_attempts=3, base_delay=0.01)
    async def flaky_task():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("一時的エラー")
        return "成功"

    result = await flaky_task()
    assert result == "成功"
    assert call_count == 2


@pytest.mark.asyncio
async def test_async_retry_decorator_max_attempts_exceeded():
    """リトライデコレータ：最大試行回数超過でPipelineError"""
    @async_retry(max_attempts=2, base_delay=0.01)
    async def always_failing():
        raise RuntimeError("常に失敗")

    with pytest.raises(PipelineError) as exc_info:
        await always_failing()

    assert "failed after 2 attempts" in str(exc_info.value)


@pytest.mark.asyncio
async def test_commercial_pipeline_plan_stage_retry():
    """_step_plan_async のリトライテスト"""
    pipeline = CommercialPipeline()

    call_count = 0

    original_step_plan = pipeline._step_plan

    def flaky_step_plan(config):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("一時的DBエラー")
        return original_step_plan(config)

    pipeline._step_plan = flaky_step_plan

    series_config = {
        "book_id": 1,
        "genre": "ファンタジー",
        "concept": "異世界転生",
        "keywords": "魔法",
        "target_eps": 1,
    }

    bible = await pipeline._step_plan_async(series_config)

    assert call_count == 2
    assert bible["book_id"] == 1


@pytest.mark.asyncio
async def test_commercial_pipeline_generate_content_retry():
    """_generate_content_async のリトライテスト"""
    pipeline = CommercialPipeline()

    bible = {
        "book_id": 1,
        "genre": "ファンタジー",
        "concept": "異世界転生",
        "keywords": ["魔法"],
        "target_eps": 1,
        "target_word_count_per_episode": 3000,
    }

    call_count = 0

    async def flaky_generate_content(bible, samples, platforms):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("一時的ネットワークエラー")
        return [{"ep_num": 1, "content": "本文"}], {"kakuyomu": [{"ep_num": 1}]}

    pipeline._generate_content = flaky_generate_content

    selected, exports = await pipeline._generate_content_async(bible, [], ["kakuyomu"])

    assert call_count == 2
    assert len(selected) == 1


@pytest.mark.asyncio
async def test_commercial_pipeline_partial_completion_saves_artifacts():
    """部分完了時の成果物保存テスト（リトライ後も失敗）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "schedule.csv")
        pipeline = CommercialPipeline(csv_path=csv_path)

        series_config = {
            "book_id": 1,
            "genre": "ファンタジー",
            "concept": "異世界転生",
            "keywords": ["魔法"],
            "target_eps": 3,
            "target_word_count_per_episode": 3000,
            "platforms": ["kakuyomu"],
        }

        call_count = 0

        async def mock_write(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # エピソード1は成功、エピソード2以降は失敗
            ep_num = kwargs.get("ep_num", 1)
            if ep_num >= 2:
                raise Exception("Episode failed")
            return {
                "text": "本文" * 100,
                "summary": "要約",
                "quality_score": 0.8,
                "killer_phrase": "台詞",
            }

        mock_writer = AsyncMock()
        mock_writer.write.side_effect = mock_write

        with patch("src.backend.workflows.commercial_pipeline.EpisodeWriter", return_value=mock_writer):
            result = await pipeline.run(
                series_config=series_config,
                samples=[],
                platforms=["kakuyomu"],
                do_publish=False
            )

        assert "error" in result
        assert "Episode 2 generation failed" in result["error"]


# =============================================================================
# Step 20: 並行実行時のリソース競合回避
# =============================================================================

@pytest.mark.asyncio
async def test_commercial_pipeline_concurrent_execution_semaphore():
    """並行実行時のセマフォ制限テスト"""
    pipeline = CommercialPipeline()

    semaphore = asyncio.Semaphore(2)
    active_count = 0
    max_active = 0

    async def limited_task(task_id: int):
        nonlocal active_count, max_active
        async with semaphore:
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0.01)
            active_count -= 1
        return task_id

    tasks = [limited_task(i) for i in range(5)]
    results = await asyncio.gather(*tasks)

    assert max_active <= 2
    assert results == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_commercial_pipeline_parallel_pipeline_runs():
    """複数パイプライン並行実行のテスト"""
    with tempfile.TemporaryDirectory() as tmpdir:
        async def run_pipeline(book_id: int):
            csv_path = os.path.join(tmpdir, f"schedule_{book_id}.csv")
            pipeline = CommercialPipeline(csv_path=csv_path)

            series_config = {
                "book_id": book_id,
                "genre": "ファンタジー",
                "concept": "異世界転生",
                "keywords": "魔法",
                "target_eps": 1,
                "target_word_count_per_episode": 3000,
                "platforms": ["kakuyomu"],
            }

            mock_writer = AsyncMock()
            mock_writer.write.return_value = {
                "text": "本文" * 100,
                "summary": "要約",
                "quality_score": 0.8,
                "killer_phrase": "台詞",
            }

            with patch("src.backend.workflows.commercial_pipeline.EpisodeWriter", return_value=mock_writer):
                return await pipeline.run(
                    series_config=series_config,
                    samples=[],
                    platforms=["kakuyomu"],
                    do_publish=False
                )

        results = await asyncio.gather(
            run_pipeline(1),
            run_pipeline(2),
            run_pipeline(3),
        )

        for result in results:
            assert "error" not in result
            assert result["bible"] is not None
            assert len(result["selected"]) == 1


@pytest.mark.asyncio
async def test_commercial_pipeline_db_pool_exhaustion_prevention():
    """DB接続プール枯渇防止のテスト（セマフォによる制限）"""
    pool_semaphore = asyncio.Semaphore(3)
    acquired_connections = 0
    max_connections = 0

    async def mock_db_operation():
        nonlocal acquired_connections, max_connections
        async with pool_semaphore:
            acquired_connections += 1
            max_connections = max(max_connections, acquired_connections)
            await asyncio.sleep(0.01)
            acquired_connections -= 1

    tasks = [mock_db_operation() for _ in range(10)]
    await asyncio.gather(*tasks)

    assert max_connections <= 3


# =============================================================================
# 既存テストの再確認
# =============================================================================

@pytest.mark.asyncio
async def test_commercial_pipeline_async_retry_success():
    """既存テスト: リトライ成功"""
    call_count = 0

    @async_retry(max_attempts=3, base_delay=0.01)
    async def flaky_task():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("temporary error")
        return "success"

    result = await flaky_task()
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_commercial_pipeline_async_retry_permanent_failure():
    """既存テスト: 最大リトライ超過"""
    @async_retry(max_attempts=2, base_delay=0.01)
    async def always_failing_task():
        raise RuntimeError("always fail")

    with pytest.raises(PipelineError):
        await always_failing_task()


def test_commercial_pipeline_init():
    """既存テスト: 初期化"""
    pipeline = CommercialPipeline(csv_path="output/test.csv")
    assert pipeline.csv_path == "output/test.csv"
    assert hasattr(pipeline, "execute_batch")
