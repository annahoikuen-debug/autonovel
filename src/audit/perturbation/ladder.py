from __future__ import annotations

"""強度ラダー構築 (M1-C)。

各擾乱変換について、baseline (変換なし) / weak (strength=1.0) /
medium (strength=2.0) / strong (strength=3.0) の4エントリを生成する。

擾乱ラダーは、判定器が「軽度の擾乱に鈍感ではないか」「重度の擾乱で
スコアが単調に下がるか」を検証するための土台となる。
"""

from dataclasses import dataclass
from typing import Literal

from src.audit.perturbation.transforms import (
    PerturbationTransform,
    TRANSFORM_REGISTRY,
)

LadderLabel = Literal["baseline", "weak", "medium", "strong"]

_STRENGTHS: dict[LadderLabel, float] = {
    "baseline": 0.0,
    "weak": 1.0,
    "medium": 2.0,
    "strong": 3.0,
}


@dataclass
class LadderEntry:
    """ラダーの1エントリ。"""

    transform_id: str
    strength: float
    label: LadderLabel
    transform: PerturbationTransform | None = None

    def apply(self, text: str) -> str:
        """テキストに変換を適用する。baseline は元のまま返す。"""
        if self.label == "baseline" or self.transform is None:
            return text
        return self.transform.apply(text)


def _make_strength_variant(
    base: PerturbationTransform, strength: float
) -> PerturbationTransform:
    """同一クラスの強度違いインスタンスを生成する。

    各変換クラスは引数なしコンストラクタを持ち、strength は
    PerturbationTransform の dataclass フィールドとして保持するため、
    再インスタンス化後に strength フィールドを上書きする。
    """
    variant = type(base)()
    variant.strength = strength
    return variant


def build_ladder(
    registry: dict[str, PerturbationTransform] | None = None,
) -> dict[str, list[LadderEntry]]:
    """全変換について強度ラダーを構築する。

    Returns:
        {transform_id: [baseline, weak, medium, strong]}
    """
    if registry is None:
        registry = TRANSFORM_REGISTRY

    ladders: dict[str, list[LadderEntry]] = {}
    for tid, base in registry.items():
        entries: list[LadderEntry] = []
        # baseline: 変換なし
        entries.append(
            LadderEntry(
                transform_id=tid,
                strength=0.0,
                label="baseline",
                transform=None,
            )
        )
        # weak / medium / strong: 強度違いインスタンス
        for label in ("weak", "medium", "strong"):
            variant = _make_strength_variant(base, _STRENGTHS[label])
            entries.append(
                LadderEntry(
                    transform_id=tid,
                    strength=_STRENGTHS[label],
                    label=label,
                    transform=variant,
                )
            )
        ladders[tid] = entries
    return ladders


__all__ = [
    "LadderEntry",
    "LadderLabel",
    "build_ladder",
    "_make_strength_variant",
]
