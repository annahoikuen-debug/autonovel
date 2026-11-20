"""
Performance unit test for SubtextEngine (Step 18).
"""

import time

import pytest

from src.narrative.subtext_engine.engine import SubtextEngine
from src.narrative.subtext_engine.models import DialogueBlock

# 実機速度に依存する wall-clock 閾値テストのため、pytest.ini の perf マーカーを付与
# （CI の通常実行 `-m "not ... and not perf ..."` から除外される。make test-perf で実行）。
pytestmark = pytest.mark.perf


def test_engine_performance_threshold():
    engine = SubtextEngine.create_default()
    sample_blocks = [
        DialogueBlock(speaker="A", lines=["「私は悲しい」"]),
        DialogueBlock(speaker="B", lines=["「なぜなら君が悪いからだ」"]),
        DialogueBlock(speaker="C", lines=["「はい」"]),
        DialogueBlock(speaker="D", lines=["「ごめんなさい」"]),
        DialogueBlock(speaker="E", lines=["地の文です。"]),
    ] * 100  # 500 blocks

    start = time.perf_counter()
    res = engine.process(sample_blocks)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert len(res) == 500
    assert elapsed_ms < 500.0, f"Processing too slow: {elapsed_ms:.2f} ms"
