from __future__ import annotations

"""擾乱ラダー評価メトリクス (M1-C 後半)。

- Spearman ρ: 強度レベルとスコアの単調相関
- 識別性: 期待軸の低下が他軸より有意に大きいか
- INV (不変性): T08/T09 などで全軸 |Δ| ≤ 閾値
- 再テスト σ: 同一入力を2回評価したときのスコア分散
"""

import math
from dataclasses import dataclass
from typing import Literal

LadderLabel = Literal["baseline", "weak", "medium", "strong"]

_STRENGTH_ORDER = {"baseline": 0, "weak": 1, "medium": 2, "strong": 3}


@dataclass
class SpearmanResult:
    rho: float
    p_value: float | None = None
    n: int = 0


def spearman_rank(x: list[float], y: list[float]) -> SpearmanResult:
    """Spearman の順位相関係数 ρ を計算する。

    同順位（タイ）がある場合は平均順位を割り当てる。
    n < 2 の場合は rho=0.0 を返す。

    Returns:
        SpearmanResult(rho, p_value, n)
        p_value は現時点では未計算（None）。
    """
    n = len(x)
    if n != len(y) or n < 2:
        return SpearmanResult(rho=0.0, p_value=None, n=n)

    def _ranks(values: list[float]) -> list[float]:
        indexed = sorted(enumerate(values), key=lambda iv: iv[1])
        ranks: list[float] = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n and indexed[j][1] == indexed[i][1]:
                j += 1
            # 同順位グループの平均順位 (1-origin)
            avg_rank = (i + 1 + j) / 2.0
            for k in range(i, j):
                ranks[indexed[k][0]] = avg_rank
            i = j
        return ranks

    rx = _ranks(x)
    ry = _ranks(y)

    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n

    num = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    den_x = math.sqrt(sum((r - mean_rx) ** 2 for r in rx))
    den_y = math.sqrt(sum((r - mean_ry) ** 2 for r in ry))

    if den_x == 0.0 or den_y == 0.0:
        return SpearmanResult(rho=0.0, p_value=None, n=n)

    rho = num / (den_x * den_y)
    # 浮動小数点誤差で [-1, 1] をわずかに超えるのをクランプ
    rho = max(-1.0, min(1.0, rho))
    return SpearmanResult(rho=round(rho, 6), p_value=None, n=n)


@dataclass
class IdentifiabilityResult:
    """識別性評価結果。

    expected_drop: 期待軸の平均スコア低下 (baseline 強度の差)
    other_drop: 他軸の平均スコア低下
    ratio: expected_drop / other_drop (other_drop=0 なら inf)
    identified: expected_drop >= other_drop * 1.5 かつ expected_drop > 0
    """

    expected_drop: float
    other_drop: float
    ratio: float
    identified: bool


def identify_axis(
    baseline_scores: dict[str, float],
    perturbed_scores: dict[str, float],
    expected_axis: str,
) -> IdentifiabilityResult:
    """擾乱適用前後の軸別スコアから識別性を評価する。

    Args:
        baseline_scores: baseline 時の {軸名: スコア}
        perturbed_scores: 擾乱適用後の {軸名: スコア}
        expected_axis: 擾乱が影響すると期待する軸名

    Returns:
        IdentifiabilityResult
    """
    axes = list(baseline_scores.keys())
    if expected_axis not in baseline_scores:
        return IdentifiabilityResult(
            expected_drop=0.0, other_drop=0.0, ratio=0.0, identified=False
        )

    expected_drop = max(0.0, baseline_scores[expected_axis] - perturbed_scores.get(expected_axis, baseline_scores[expected_axis]))

    other_drops = []
    for ax in axes:
        if ax == expected_axis:
            continue
        b = baseline_scores[ax]
        p = perturbed_scores.get(ax, b)
        other_drops.append(max(0.0, b - p))

    other_drop = sum(other_drops) / len(other_drops) if other_drops else 0.0

    if other_drop > 0:
        ratio = expected_drop / other_drop
    else:
        ratio = float("inf") if expected_drop > 0 else 0.0

    identified = expected_drop > 0 and expected_drop >= other_drop * 1.5
    return IdentifiabilityResult(
        expected_drop=round(expected_drop, 6),
        other_drop=round(other_drop, 6),
        ratio=round(ratio, 6) if ratio != float("inf") else float("inf"),
        identified=identified,
    )


@dataclass
class InvarianceResult:
    """INV (不変性) 評価結果。

    max_delta: 全軸の最大 |Δ|
    passed: max_delta <= 閾値
    """

    max_delta: float
    passed: bool


def check_invariance(
    baseline_scores: dict[str, float],
    perturbed_scores: dict[str, float],
    threshold: float = 3.0,
) -> InvarianceResult:
    """INV (不変性) を評価する。

    T08 (一貫改名) / T09 (句読点正規化) など、意味が変わらない変換では
    全軸のスコア変化が閾値以内であることを期待する。
    """
    max_delta = 0.0
    for ax, b in baseline_scores.items():
        p = perturbed_scores.get(ax, b)
        delta = abs(b - p)
        if delta > max_delta:
            max_delta = delta
    return InvarianceResult(max_delta=round(max_delta, 6), passed=max_delta <= threshold)


@dataclass
class RetestResult:
    """再テスト σ 評価結果。

    sigma: 2回評価の標準偏差 (母標準偏差)
    passed: sigma <= 閾値
    """

    sigma: float
    passed: bool


def check_retest_stability(
    score_run1: float,
    score_run2: float,
    threshold: float = 5.0,
) -> RetestResult:
    """再テスト安定性を評価する。

    同一入力を2回評価したスコアの母標準偏差が閾値以内かを返す。
    """
    mean = (score_run1 + score_run2) / 2.0
    sigma = math.sqrt(((score_run1 - mean) ** 2 + (score_run2 - mean) ** 2) / 2.0)
    return RetestResult(sigma=round(sigma, 6), passed=sigma <= threshold)


__all__ = [
    "SpearmanResult",
    "IdentifiabilityResult",
    "InvarianceResult",
    "RetestResult",
    "spearman_rank",
    "identify_axis",
    "check_invariance",
    "check_retest_stability",
    "LadderLabel",
    "_STRENGTH_ORDER",
]
