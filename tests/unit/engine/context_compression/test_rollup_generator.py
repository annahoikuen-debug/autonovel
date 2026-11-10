"""RollupGenerator の単体テスト (PLAN_M1 Step 6).

境界判定・章/巻ロールアップ生成・文字数クランプ・LLM 失敗時の fail-open を
検証する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.context_compression.rollup_config import RollupConfig
from src.engine.context_compression.rollup_generator import RollupGenerator


class TestRollupGeneratorBoundary:
    """章・巻境界判定のテスト。"""

    @pytest.fixture
    def cfg(self):
        return RollupConfig(
            episodes_per_block=10,
            blocks_per_volume=5,
            block_digest_chars=300,
            volume_digest_chars=800,
        )

    @pytest.mark.parametrize(
        "ep,expected",
        [
            (1, False),
            (9, False),
            (10, True),
            (11, False),
            (20, True),
            (50, True),  # 10*5 = 50 巻境界
            (51, False),
            (100, True),
        ],
    )
    def test_should_generate_block(self, cfg, ep, expected):
        gen = RollupGenerator(cfg)
        assert gen.should_generate_block(ep) is expected, f"ep={ep}"

    @pytest.mark.parametrize(
        "ep,expected",
        [
            (1, False),
            (49, False),
            (50, True),  # 10話/章 × 5章 = 50話/巻
            (51, False),
            (100, True),
        ],
    )
    def test_should_generate_volume(self, cfg, ep, expected):
        gen = RollupGenerator(cfg)
        assert gen.should_generate_volume(ep) is expected, f"ep={ep}"


class MockLLM:
    """generate(prompt=, temperature=) を持つシンプルなモック LLM。"""

    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def generate(self, prompt=None, temperature=0.1):
        self.calls.append((prompt, temperature))
        return self.response


class TestRollupGeneratorBlock:
    """章ロールアップ生成のテスト。"""

    @pytest.fixture
    def cfg(self):
        return RollupConfig(
            episodes_per_block=10,
            blocks_per_volume=5,
            block_digest_chars=300,
            volume_digest_chars=800,
        )

    @pytest.mark.asyncio
    async def test_generate_block_rollup(self, cfg):
        member_digests = {
            1: "第1話: アルスは剣を入手した。",
            2: "第2話: アルスは村を出た。",
            10: "第10話: アルスは王都に到着した。",
        }
        mock_llm = MockLLM(response="アルスは剣を入手し、村を出て王都に到着した。")
        gen = RollupGenerator(cfg, llm=mock_llm)

        result = await gen.generate_block_rollup(
            book_id=1, ep_range=(1, 10), member_digests=member_digests
        )

        assert result == "アルスは剣を入手し、村を出て王都に到着した。"
        assert len(mock_llm.calls) == 1
        assert "第1話" in mock_llm.calls[0][0]
        assert "第10話" in mock_llm.calls[0][0]
        assert mock_llm.calls[0][1] == 0.1

    @pytest.mark.asyncio
    async def test_generate_block_rollup_clamp(self, cfg):
        """300字を超える場合はクランプされる。"""
        long_text = "あ" * 400
        mock_llm = MockLLM(response=long_text)
        gen = RollupGenerator(cfg, llm=mock_llm)

        member_digests = {1: "d1", 10: "d10"}
        result = await gen.generate_block_rollup(
            book_id=1, ep_range=(1, 10), member_digests=member_digests
        )

        assert len(result) <= cfg.block_digest_chars
        assert result.endswith("...")

    @pytest.mark.asyncio
    async def test_generate_block_rollup_llm_none(self, cfg):
        """LLM 未設定時は None を返す（fail-open）。"""
        gen = RollupGenerator(cfg, llm=None)
        result = await gen.generate_block_rollup(
            book_id=1, ep_range=(1, 10), member_digests={1: "d1"}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_block_rollup_empty(self, cfg):
        """メンバ digests が空の場合は None。"""
        mock_llm = MockLLM(response="x")
        gen = RollupGenerator(cfg, llm=mock_llm)
        result = await gen.generate_block_rollup(
            book_id=1, ep_range=(1, 10), member_digests={}
        )
        assert result is None
        assert len(mock_llm.calls) == 0  # LLM 未呼び出し

    @pytest.mark.asyncio
    async def test_generate_block_rollup_llm_arg_override(self, cfg):
        """llm 引数で一時的に LLM を差し替えられる。"""
        default_llm = MockLLM(response="default")
        override_llm = MockLLM(response="override")
        gen = RollupGenerator(cfg, llm=default_llm)

        member_digests = {1: "d1"}
        result = await gen.generate_block_rollup(
            book_id=1, ep_range=(1, 10), member_digests=member_digests, llm=override_llm
        )

        assert result == "override"
        # self.llm は元に戻されている（default_llm の呼び出し回数は増えていない）
        assert len(default_llm.calls) == 0
        assert len(override_llm.calls) == 1


class TestRollupGeneratorVolume:
    """巻ロールアップ生成のテスト。"""

    @pytest.fixture
    def cfg(self):
        return RollupConfig(
            episodes_per_block=10,
            blocks_per_volume=5,
            block_digest_chars=300,
            volume_digest_chars=800,
        )

    @pytest.mark.asyncio
    async def test_generate_volume_rollup(self, cfg):
        block_rollups = [
            (1, 10, "章1の要約。"),
            (11, 20, "章2の要約。"),
        ]
        mock_llm = MockLLM(response="巻の総合要約。")
        gen = RollupGenerator(cfg, llm=mock_llm)

        result = await gen.generate_volume_rollup(
            book_id=1, block_rollups=block_rollups
        )

        assert result == "巻の総合要約。"
        assert len(mock_llm.calls) == 1
        assert "第1話〜第10話" in mock_llm.calls[0][0]
        assert "第11話〜第20話" in mock_llm.calls[0][0]

    @pytest.mark.asyncio
    async def test_generate_volume_rollup_clamp(self, cfg):
        long_text = "あ" * 1000
        mock_llm = MockLLM(response=long_text)
        gen = RollupGenerator(cfg, llm=mock_llm)

        block_rollups = [(1, 10, "章1")]
        result = await gen.generate_volume_rollup(
            book_id=1, block_rollups=block_rollups
        )

        assert len(result) <= cfg.volume_digest_chars
        assert result.endswith("...")

    @pytest.mark.asyncio
    async def test_generate_volume_rollup_llm_none(self, cfg):
        gen = RollupGenerator(cfg, llm=None)
        result = await gen.generate_volume_rollup(
            book_id=1, block_rollups=[(1, 10, "章1")]
        )
        assert result is None
