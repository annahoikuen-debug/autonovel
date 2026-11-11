"""事実密度メトリクスのテスト (PLAN_M1 Step 22).

Chain-of-Density (CoD) 方式で cod_rounds=2 時に、
1 pass 目の要約をさらに圧縮する 2 回目の LLM 呼び出しが行われ、
情報密度（文字数あたりの情報量）が維持・向上することを検証する。

cod_rounds=1 は現行の 1 pass と完全に同一（後方互換）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.engine.context_compression.rollup_config import RollupConfig
from src.engine.context_compression.rollup_generator import RollupGenerator


class _CountingLLM:
    """LLM 呼び出し回数と渡されたプロンプトを記録するモック。"""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.call_count = 0
        self.prompts: list[str] = []

    def generate(self, prompt: str, temperature: float = 0.1):
        self.call_count += 1
        self.prompts.append(prompt)
        idx = min(self.call_count - 1, len(self.responses) - 1)
        return self.responses[idx]


class TestFactDensityCod:
    """Cod ラウンド数と事実密度の関係をテストする。"""

    @pytest.fixture
    def cfg(self):
        return RollupConfig(
            rollup_enabled=True,
            block_digest_chars=200,
            volume_digest_chars=500,
            cod_rounds=1,
        )

    @pytest.mark.asyncio
    async def test_cod_rounds_1_is_single_llm_call(self, cfg):
        """cod_rounds=1 では LLM 呼び出しが 1 回（現行と同一）。"""
        llm = _CountingLLM(["第1〜10話: 封印が解けた。少年が旅に出た。"])
        gen = RollupGenerator(cfg, llm=llm)

        result = await gen.generate_block_rollup(
            1, (1, 10), {1: "第1話: 封印があった。", 2: "第2話: 封印が解けた。"}
        )

        assert llm.call_count == 1, f"cod_rounds=1 で呼び出し回数が 1 回でない: {llm.call_count}"
        assert result == "第1〜10話: 封印が解けた。少年が旅に出た。"

    @pytest.mark.asyncio
    async def test_cod_rounds_2_is_two_llm_calls(self, cfg):
        """cod_rounds=2 では LLM 呼び出しが 2 回（2 回目は圧縮パス）。"""
        llm = _CountingLLM(
            [
                "第1〜10話: 封印が解けた。少年が旅に出た。仲間も増えた。",  # 1 pass 目
                "第1〜10話: 封印解け、少年旅立つ。仲間増加。",  # 2 pass 目（圧縮）
            ]
        )
        gen = RollupGenerator(cfg, llm=llm)

        result = await gen.generate_block_rollup(
            1, (1, 10), {1: "第1話: 封印があった。", 2: "第2話: 封印が解けた。"},
            cod_rounds=2,
        )

        assert llm.call_count == 2, f"cod_rounds=2 で呼び出し回数が 2 回でない: {llm.call_count}"
        # 2 pass 目の結果が採用される
        assert result == "第1〜10話: 封印解け、少年旅立つ。仲間増加。"
        # 2 回目のプロンプトは「圧縮」を指示している
        assert "圧縮" in llm.prompts[1], f"2 回目プロンプトに圧縮指示が含まれていない: {llm.prompts[1]}"

    @pytest.mark.asyncio
    async def test_cod_rounds_2_volume_rollup(self, cfg):
        """巻ロールアップでも cod_rounds=2 で 2 回呼び出し。"""
        llm = _CountingLLM(
            [
                "第1〜50話: 封印が解け、少年は王となった。",
                "第1〜50話: 封印解け、少年王になる。",
            ]
        )
        gen = RollupGenerator(cfg, llm=llm)

        block_rollups = [
            (1, 10, "第1〜10話: 封印があった。"),
            (11, 20, "第11〜20話: 封印が解けた。"),
        ]
        result = await gen.generate_volume_rollup(1, block_rollups, cod_rounds=2)

        assert llm.call_count == 2, f"巻ロールアップ cod_rounds=2 で呼び出し回数が 2 回でない: {llm.call_count}"
        assert result == "第1〜50話: 封印解け、少年王になる。"

    @pytest.mark.asyncio
    async def test_cod_rounds_3_is_three_llm_calls(self, cfg):
        """cod_rounds=3 では LLM 呼び出しが 3 回。"""
        llm = _CountingLLM(
            [
                "pass1 結果",
                "pass2 結果",
                "pass3 結果",
            ]
        )
        gen = RollupGenerator(cfg, llm=llm)

        result = await gen.generate_block_rollup(
            1, (1, 10), {1: "第1話: テスト。"}, cod_rounds=3
        )

        assert llm.call_count == 3, f"cod_rounds=3 で呼び出し回数が 3 回でない: {llm.call_count}"
        assert result == "pass3 結果"

    @pytest.mark.asyncio
    async def test_cod_rounds_0_falls_back_to_single_call(self, cfg):
        """cod_rounds=0 では max(0, rounds-1)=0 で 1 回呼び出し（現行と同一）。"""
        llm = _CountingLLM(["単一 pass 結果"])
        gen = RollupGenerator(cfg, llm=llm)

        result = await gen.generate_block_rollup(
            1, (1, 10), {1: "第1話: テスト。"}, cod_rounds=0
        )

        assert llm.call_count == 1
        assert result == "単一 pass 結果"

    @pytest.mark.asyncio
    async def test_llm_none_returns_none_even_with_cod(self, cfg):
        """LLM 未設定時は cod_rounds に関わらず None を返す（fail-open）。"""
        gen = RollupGenerator(cfg, llm=None)

        result = await gen.generate_block_rollup(
            1, (1, 10), {1: "第1話: テスト。"}, cod_rounds=2
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_density_monotonic_or_equal(self, cfg):
        """事実密度メトリクス: 2 pass 目の出力文字数は 1 pass 目以下か同等（圧縮による密度向上）。

        モック LLM が 2 pass 目で短い文字列を返す場合、密度が向上していると判定する。
        """
        llm = _CountingLLM(
            [
                "あ" * 150,  # 1 pass 目: 長い要約
                "あ" * 50,  # 2 pass 目: 圧縮済み短い要約
            ]
        )
        gen = RollupGenerator(cfg, llm=llm)

        result = await gen.generate_block_rollup(
            1, (1, 10), {1: "第1話: テスト。" * 10}, cod_rounds=2
        )

        assert result == "あ" * 50
        assert len(result) <= 150, "2 pass 目は 1 pass 目以下の文字数（圧縮による密度向上）であるべき"
