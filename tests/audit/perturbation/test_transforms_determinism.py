"""T-P1-1: 擾乱変換の決定性テスト。

同一 seed で 5 回 apply したとき、出力がすべてバイト一致することを保証する。
"""

from __future__ import annotations

from src.audit.perturbation import TRANSFORM_REGISTRY

_TEST_TEXT = (
    "アルトは古いダンジョンの入り口に立っていた。剣を握る手に汗が光る。\n"
    "「ここだ」とアルトは呟いた。闇が奥から息をしている。\n"
    "何かが始まろうとしていた。運命の歯車が回り出す。\n"
    "アルトは深呼吸をして、一歩を踏み出した。\n"
)


def test_all_transforms_deterministic():
    """全変換が同一 seed で 5 回実行 → 出力バイト一致。"""
    for tid, transform in TRANSFORM_REGISTRY.items():
        outputs = [transform.apply(_TEST_TEXT) for _ in range(5)]
        first = outputs[0]
        for i, out in enumerate(outputs[1:], start=2):
            assert out == first, (
                f"{transform.id}: {i} 回目と1回目の出力が一致しません (非決定的)"
            )


def test_transforms_return_str():
    """全変換が str を返す。"""
    for tid, transform in TRANSFORM_REGISTRY.items():
        result = transform.apply(_TEST_TEXT)
        assert isinstance(result, str), f"{transform.id}: 戻り値が str ではない"
