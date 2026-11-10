"""PinnedFactsGenerator の単体テスト (PLAN_M1 Step 15).

LLM 不使用で契約伏線・期限超過伏線・前話 digest から head/tail を抽出する
動作を検証する。
"""

from __future__ import annotations

import pytest

from src.engine.context_compression.pinned_facts import PinnedFactsGenerator
from src.engine.context_compression.rollup_config import RollupConfig


class TestPinnedFactsGenerator:
    """PinnedFactsGenerator のテストスイート。"""

    @pytest.fixture
    def cfg(self):
        return RollupConfig(
            rollup_enabled=True,
            pinned_max_chars=300,
            pinned_tail_max_chars=300,
        )

    @pytest.fixture
    def gen(self, cfg):
        return PinnedFactsGenerator(cfg)

    def test_empty_input_returns_empty_facts(self, gen):
        """入力がない場合は head/tail とも空。"""
        result = gen.generate()
        assert result.head == ""
        assert result.tail == ""

    def test_overdue_foreshadowing_is_included(self, gen):
        """期限超過伏線が head/tail に含まれる。"""
        result = gen.generate(
            overdue_foreshadowings=[{"title": "竜の鱗の行方"}],
        )
        assert "【期限超過】竜の鱗の行方 の回収が未完了" in result.head
        assert "☐ 【期限超過】竜の鱗の行方 の回収が未完了" in result.tail

    def test_contract_foreshadowing_is_included(self, gen):
        """本話契約伏線が head/tail に含まれる。"""
        result = gen.generate(
            contract_foreshadowings=[{"title": "古代の封印"}],
        )
        assert "【本話回収必須】古代の封印" in result.head
        assert "☐ 【本話回収必須】古代の封印" in result.tail

    def test_state_change_keyword_extracted(self, gen):
        """前話 digest の状態変化キーワードを含む行が抽出される。"""
        prev_digest = (
            "第20話: アルスは剣を入手した。村を出た。\n"
            "アルスは敵を倒した。新たな仲間が加わった。"
        )
        result = gen.generate(prev_digest_text=prev_digest)
        assert "【状態変化】第20話: アルスは剣を入手した。村を出た。" in result.head
        assert "【状態変化】アルスは敵を倒した。新たな仲間が加わった。" in result.head

    def test_priority_order_overdue_then_contract_then_state(self, gen):
        """優先順: 期限超過 > 契約 > 状態変化。"""
        prev_digest = "第20話: アルスは剣を入手した。"
        result = gen.generate(
            overdue_foreshadowings=[{"title": "期限切れ伏線"}],
            contract_foreshadowings=[{"title": "本話伏線"}],
            prev_digest_text=prev_digest,
        )
        head_lines = result.head.splitlines()
        assert head_lines[0] == "- 【期限超過】期限切れ伏線 の回収が未完了"
        assert head_lines[1] == "- 【本話回収必須】本話伏線"
        assert head_lines[2] == "- 【状態変化】第20話: アルスは剣を入手した。"

    def test_head_clamped_at_max_chars(self):
        """head が pinned_max_chars でクランプされる。"""
        cfg = RollupConfig(pinned_max_chars=50)
        gen = PinnedFactsGenerator(cfg)
        long_title = "あ" * 100
        result = gen.generate(
            overdue_foreshadowings=[{"title": long_title}],
        )
        assert len(result.head) <= cfg.pinned_max_chars
        assert result.head.endswith("…")

    def test_tail_clamped_at_max_chars(self):
        """tail が pinned_tail_max_chars でクランプされる。"""
        cfg = RollupConfig(pinned_tail_max_chars=50)
        gen = PinnedFactsGenerator(cfg)
        long_title = "あ" * 100
        result = gen.generate(
            contract_foreshadowings=[{"title": long_title}],
        )
        assert len(result.tail) <= cfg.pinned_tail_max_chars
        assert result.tail.endswith("…")

    def test_from_env_defaults(self):
        """RollupConfig.from_env の既定値で pinned_max_chars=300。"""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=True):
            cfg = RollupConfig.from_env()
            assert cfg.pinned_max_chars == 300
            assert cfg.pinned_tail_max_chars == 300

    def test_from_env_override(self):
        """環境変数で上書きできる。"""
        import os
        from unittest.mock import patch

        with patch.dict(
            os.environ,
            {
                "PINNED_FACTS_MAX_CHARS": "100",
                "PINNED_FACTS_TAIL_MAX_CHARS": "200",
            },
            clear=True,
        ):
            cfg = RollupConfig.from_env()
            assert cfg.pinned_max_chars == 100
            assert cfg.pinned_tail_max_chars == 200
