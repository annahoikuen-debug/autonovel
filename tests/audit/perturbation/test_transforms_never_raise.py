"""T-P1-6: 擾乱変換の不例外性テスト。

ランダムな日本語風テキストに対し、全変換が例外を出さず、
非空の文字列を返すことを保証する。
"""

from __future__ import annotations

import random

from src.audit.perturbation import TRANSFORM_REGISTRY

_KANA = "あいうえおかきくけこさしすせそたちつてとなにぬねの"
_KANJI = "アルトダンジョン剣魔法扉闇闇光扉騎士王国"
_PUNCT = "。！？”」、、「」"


def _make_random_text(rng: random.Random, min_paras: int = 3, max_paras: int = 8) -> str:
    """日本語風のランダムテキストを生成する。"""
    n_paras = rng.randint(min_paras, max_paras)
    paragraphs = []
    for _ in range(n_paras):
        n_sentences = rng.randint(1, 4)
        sentences = []
        for _ in range(n_sentences):
            n_chars = rng.randint(5, 30)
            s = "".join(rng.choice(_KANA + _KANJI + _PUNCT) for _ in range(n_chars))
            sentences.append(s)
        paragraphs.append("".join(sentences))
    return "\n\n".join(paragraphs)


def test_all_transforms_never_raise_on_random_text():
    """ランダムテキストに対し全変換が例外を出さず非空を返す。"""
    rng = random.Random(12345)
    for _ in range(20):
        text = _make_random_text(rng)
        for tid, transform in TRANSFORM_REGISTRY.items():
            result = transform.apply(text)
            assert isinstance(result, str), f"{transform.id}: 戻り値が str ではない"
            assert result, f"{transform.id}: ランダムテキストで空の出力"


def test_all_transforms_handle_empty_and_whitespace():
    """空文字・空白のみ・改行のみの入力でも例外を出さない。"""
    for tid, transform in TRANSFORM_REGISTRY.items():
        for bad in ["", "   ", "\n", "\n\n", " \t \n"]:
            try:
                result = transform.apply(bad)
            except Exception as e:  # noqa: BLE001 - 不例外性を検証するため広く捕捉
                raise AssertionError(f"{transform.id}: 入力 {bad!r} で例外 {e!r}")
            assert isinstance(result, str)
