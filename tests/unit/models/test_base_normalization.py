"""`src/models/base.py` の正規化ヘルパーの回帰テスト。

このテストが固定する問題
----------------------
1. ``extract_int`` の語典参照順
   旧実装は ``word_map`` の**定義順**で部分一致を判定していたため、
   短いキーを含む長いキー（``"high"`` ⊂ ``"very high"``、
   ``"高"`` ⊂ ``"最高"``）が先に当たり、正しくても常に低めの値を返していた。
   ``extract_int("very high")`` は 70（本来 85）、
   ``extract_int("最高")`` は 80（本来 100）になっていた。
   長い語から先に判定するよう修正済み。

2. ``normalize_chain_phase`` の正規値潰し
   旧実装は入力が ``ChainPhase`` の正当値かどうかを**先に**判定せず、
   大文字小文字だけの部分一致で改めて命名していた。そのため
   ``normalize_chain_phase("Hate")`` が ``"Hate"`` ではなく
   ``"Friction"`` に書き換えられていた。修正済み。
"""

from __future__ import annotations

import pytest

from src.models.base import extract_int, normalize_chain_phase


class TestExtractInt:
    def test_longest_word_wins_japanese(self):
        """``"最高"`` は ``"高"`` より長いキーワードとして判定される。"""
        assert extract_int("最高") == 100

    def test_longest_word_wins_english(self):
        """``"very high"`` は ``"high"`` より先に判定される。"""
        assert extract_int("very high") == 85

    def test_plain_high_is_still_70(self):
        """``"high"`` 単体の判定は変わらない（70）。"""
        assert extract_int("high") == 70

    def test_plain_gao_is_still_80(self):
        """``"高"`` 単体の判定は変わらない（80）。"""
        assert extract_int("高") == 80

    def test_numeric_extraction_still_works(self):
        """数値抽出の挙動は変えていない。"""
        assert extract_int("80%") == 80
        assert extract_int(70) == 70
        assert extract_int("") == 0


class TestNormalizeChainPhase:
    def test_legal_value_hate_is_preserved(self):
        """``ChainPhase`` の正当値 ``"Hate"`` は書き換えられない。"""
        assert normalize_chain_phase("Hate") == "Hate"

    @pytest.mark.parametrize(
        "phase",
        ["Friction", "Prep", "Payoff", "Discovery", "Bonding", "Fulfillment", "Hate"],
    )
    def test_all_legal_values_are_preserved(self, phase: str):
        """全ての正式値について ``f(x) == x`` が成り立つ。"""
        assert normalize_chain_phase(phase) == phase

    def test_alias_still_maps_to_hate(self):
        """正規化（別名から正式値への写像）は機能し続けている。"""
        assert normalize_chain_phase("憎悪") == "Hate"
        assert normalize_chain_phase("ヘイト") == "Hate"
        assert normalize_chain_phase("hate") == "Hate"

    def test_unknown_value_falls_back_to_friction(self):
        assert normalize_chain_phase("unknown-phase") == "Friction"
