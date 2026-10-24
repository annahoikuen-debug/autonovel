"""
config/erotic_vocabulary_ext.py
エロティックボキャブラリー拡張モジュール（スタブ）
実際の実装は config/erotic_vocabulary.py に委譲。
"""

from config.erotic_vocabulary import get_vocabulary_for_tier


def get_vocabulary_for_tier_ext(tier: str) -> dict:
    """拡張ティアの語彙を返す。intense 以外は erotic_vocabulary に委譲する。

    Args:
        tier: ティア名 ("intense" / "mild" / "moderate" / "full")

    Returns:
        dict: "metaphors", "onomatopoeia", "psychology" のリスト
    """
    return get_vocabulary_for_tier(tier)
