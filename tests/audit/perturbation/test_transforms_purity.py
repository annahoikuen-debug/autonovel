"""T-P1-2: 擾乱変換の純粋性・非破壊・境界テスト。

- 入力文字列が mutate されない
- 出力は非空
- min_chars 未満の入力は元のまま返される
- \r\n (CRLF) を含む入力でも正しく動作する
"""

from __future__ import annotations

from src.audit.perturbation import TRANSFORM_REGISTRY

_TEST_TEXT = (
    "アルトは古いダンジョンの入り口に立っていた。剣を握る手に汗が光る。\n"
    "「ここだ」とアルトは呟いた。闇が奥から息をしている。\n"
    "何かが始まろうとしていた。運命の歯車が回り出す。\n"
)

_SHORT_TEXT = "短い。"


def test_input_not_mutated():
    """入力文字列の内容が変わらない（str は不変なので参照も保持される）。"""
    for tid, transform in TRANSFORM_REGISTRY.items():
        before = _TEST_TEXT
        _ = transform.apply(before)
        assert before == _TEST_TEXT, f"{transform.id}: 入力が変更された"


def test_output_non_empty():
    """出力は必ず非空。"""
    for tid, transform in TRANSFORM_REGISTRY.items():
        result = transform.apply(_TEST_TEXT)
        assert result, f"{transform.id}: 出力が空"


def test_min_chars_bypass():
    """min_chars 未満の入力は元のまま返される。"""
    for tid, transform in TRANSFORM_REGISTRY.items():
        result = transform.apply(_SHORT_TEXT)
        assert result == _SHORT_TEXT, (
            f"{transform.id}: min_chars 未満だが元のテキストと異なる出力 ({result!r})"
        )


def test_crlf_input_handled():
    """CRLF (\\r\\n) を含む入力でも例外が出ず、非空の出力を返す。"""
    crlf_text = _TEST_TEXT.replace("\n", "\r\n")
    for tid, transform in TRANSFORM_REGISTRY.items():
        result = transform.apply(crlf_text)
        assert result, f"{transform.id}: CRLF 入力で空の出力"
        assert isinstance(result, str)
