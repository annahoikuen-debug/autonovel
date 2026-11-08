"""PDCA 既定値 (max_regenerations=0) が auto_regenerate を無視しないことを検証するテスト.

WritingService.generate_episodes(..., auto_regenerate=True, max_retries=N) が
明示指定された場合、pdca_controller の max_regenerations=0 既定値によって
黙って無視されてはならない。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.backend.writing_service import WritingService


def _make_service() -> tuple[WritingService, MagicMock, MagicMock]:
    mock_writer = MagicMock()
    mock_writer.generate_episodes = AsyncMock(return_value=3000)

    mock_calculator = MagicMock()
    mock_calculator.calculate = AsyncMock(
        return_value=MagicMock(
            overall_score=80.0,
            structure_score=80.0,
            coherency_score=80.0,
            factual_grounding_score=80.0,
            visual_textual_synergy_score=80.0,
            reader_experience_score=80.0,
            regeneration_triggered=False,
            low_dimensions=[],
            regeneration_actions=[],
        )
    )

    service = WritingService(
        writer=mock_writer,
        repo=MagicMock(),
        pm=MagicMock(),
        style_rag=MagicMock(),
        ctx_mgr=MagicMock(),
        reporter_factory=MagicMock(),
        book_score_calculator=mock_calculator,
        score_threshold=70.0,
    )
    return service, mock_writer, mock_calculator


@pytest.mark.asyncio
async def test_auto_regenerate_true_triggers_score_calculation() -> None:
    """auto_regenerate=True, max_retries=3 なら book_score_calculator.calculate が呼ばれる."""
    service, mock_writer, mock_calculator = _make_service()

    # _pdca_runner.run_pdca_cycle をモック化（_trigger_pdca_rewrite 内で呼ばれる）
    service._pdca_runner = MagicMock()
    service._pdca_runner.run_pdca_cycle = AsyncMock(
        return_value=("draft", MagicMock(initial_score=50.0, final_score=80.0, converged=True))
    )

    # 1回目は低スコア (再生成トリガー)、2回目は高スコア (ループ終了)
    low_score = MagicMock(
        overall_score=50.0,
        structure_score=50.0,
        coherency_score=50.0,
        factual_grounding_score=50.0,
        visual_textual_synergy_score=50.0,
        reader_experience_score=50.0,
        regeneration_triggered=True,
        low_dimensions=[],
        regeneration_actions=[],
    )
    high_score = MagicMock(
        overall_score=80.0,
        structure_score=80.0,
        coherency_score=80.0,
        factual_grounding_score=80.0,
        visual_textual_synergy_score=80.0,
        reader_experience_score=80.0,
        regeneration_triggered=False,
        low_dimensions=[],
        regeneration_actions=[],
    )
    mock_calculator.calculate.side_effect = [
        low_score,   # 1回目: 低スコア → 再生成トリガー
        high_score,  # 2回目: 高スコア → ループ終了
        high_score,  # 予備（_trigger_pdca_rewrite 内で計算が走る場合の保険）
        high_score,
    ]

    await service.generate_episodes(
        book_id=1, start_ep=1, end_ep=1,
        passion=0.8, target_word_count=3000,
        is_easy_mode=False, reporter=MagicMock(),
        auto_regenerate=True, max_retries=3,
    )

    # auto_regenerate=True なら calculate は最低1回呼ばれる
    assert mock_calculator.calculate.call_count >= 1, (
        f"calculate が呼ばれていません: call_count={mock_calculator.calculate.call_count}"
    )
    # writer も初回 + 再生成 で2回呼ばれる
    assert mock_writer.generate_episodes.call_count == 2, (
        f"writer.generate_episodes が2回呼ばれるべき: call_count={mock_writer.generate_episodes.call_count}"
    )


@pytest.mark.asyncio
async def test_auto_regenerate_false_skips_score_calculation() -> None:
    """auto_regenerate=False なら calculate は呼ばれない（無条件に回らない）."""
    service, mock_writer, mock_calculator = _make_service()

    await service.generate_episodes(
        book_id=1, start_ep=1, end_ep=1,
        passion=0.8, target_word_count=3000,
        is_easy_mode=False, reporter=MagicMock(),
        auto_regenerate=False, max_retries=3,
    )

    # auto_regenerate=False なら calculate は呼ばれない
    assert mock_calculator.calculate.call_count == 0, (
        f"auto_regenerate=False で calculate が呼ばれています: call_count={mock_calculator.calculate.call_count}"
    )
    # writer は初回1回のみ
    assert mock_writer.generate_episodes.call_count == 1, (
        f"writer.generate_episodes が1回呼ばれるべき: call_count={mock_writer.generate_episodes.call_count}"
    )


@pytest.mark.asyncio
async def test_auto_regenerate_true_with_max_retries_zero_skips_calculation() -> None:
    """auto_regenerate=True でも max_retries=0 を明示指定すれば calculate は呼ばれない
    （現状維持：再生成ループに到達しない）."""
    service, mock_writer, mock_calculator = _make_service()

    await service.generate_episodes(
        book_id=1, start_ep=1, end_ep=1,
        passion=0.8, target_word_count=3000,
        is_easy_mode=False, reporter=MagicMock(),
        auto_regenerate=True, max_retries=0,
    )

    assert mock_calculator.calculate.call_count == 0, (
        f"max_retries=0 で calculate が呼ばれています: call_count={mock_calculator.calculate.call_count}"
    )
    assert mock_writer.generate_episodes.call_count == 1
