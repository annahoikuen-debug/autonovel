"""媒体ごとの ** contracting 契約** が話数によらず守られることの回帰テスト。

レビューで発見された破绽は「web_volume@40 と long_serial だけを見ていた」ことに
起因する.Test 側は **破綻域を明示的に含める** こと。
"""
from __future__ import annotations

import itertools

import pytest

from config.story_spine import LENGTHS, MARKETS, PATTERNS, resolve_spine

# 破綻域（含めることが本テストの意義）。web_volume の 40 話だけを发呆 sees していたのがバグ。
RISKY_EPS = (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 40, 100, 300)


@pytest.mark.parametrize("eps", [3, 4, 5, 6, 8, 10])
@pytest.mark.parametrize(
    "pattern", ["exile_rise", "detective_mystery", "death_loop", "avenger_dark"]
)
def test_web_market_ends_with_volume_hook_when_there_is_a_next_volume(pattern: str, eps: int):
    """Web 連載は 2 話以上で話末の引きで終わる。"""
    spine = resolve_spine(pattern, "short", "web", eps)
    assert spine.keys[-1] == "volume_hook", (
        f"{pattern}@{eps}: 最後が {spine.keys[-1]!r}（ending_contract 違反） keys={spine.keys}"
    )


def test_web_volume_hook_contract_holds_across_full_matrix():
    """38 パターン × 15 話数の全数走査。**1 件も例外を認めない**。"""
    offenders = []
    for pattern in sorted(PATTERNS):
        for eps in RISKY_EPS:
            if eps < 2:
                continue  # 1 話作品に「次巻への引き」は成立しない（契約の定義外）
            spine = resolve_spine(pattern, "short", "web", eps)
            if spine.keys[-1] != "volume_hook":
                offenders.append(f"{pattern}@{eps}: {spine.keys[-3:]}")
    assert not offenders, f"web の ending_contract 違反 {len(offenders)} 件:\n" + "\n".join(offenders)


@pytest.mark.parametrize("eps", [1, 5, 12, 20, 40])
@pytest.mark.parametrize("market", ["light_novel", "single_shot", "general"])
def test_non_web_markets_never_force_volume_hook(market: str, eps: int):
    """Web 以外は「次への引き」を強制しない（逆方向の契約も守る）。"""
    for pattern in ("exile_rise", "detective_mystery", "gourmet_conqueror"):
        spine = resolve_spine(pattern, "single_volume", market, eps)
        assert "volume_hook" not in spine.keys, (
            f"{market} に volume_hook が混入: {spine.keys}"
        )


def test_three_invariants_survive_the_volume_hook_fix():
    """**修正で 3 不変条件を壊していないことの保証**。"""
    for pattern in sorted(PATTERNS):
        for eps in (2, 3, 4, 8, 20, 40):
            keys = resolve_spine(pattern, "short", "web", eps).keys
            assert keys[0] in ("inciting", "humiliation", "cold_open", "revelation"), (
                f"{pattern}@{eps}: 先頭が {keys[0]!r}"
            )
            assert "midpoint_reversal" in keys, f"{pattern}@{eps}: 中点反転が消えた"
            assert "climax" in keys, f"{pattern}@{eps}: クライマックスが消えた"


def test_beat_keys_are_unique_in_every_resolution():
    """**38×6×4×3 = 2,736 ケースでキーが重複しないこと**（重複 8 件の回帰）。"""
    offenders = []
    for p, length, market in itertools.product(
        sorted(PATTERNS), sorted(LENGTHS), sorted(MARKETS)
    ):
        lo, hi = LENGTHS[length]["eps_range"]
        for eps in (lo, (lo + hi) // 2, hi):
            keys = resolve_spine(p, length, market, eps).keys
            dup = {k for k in keys if keys.count(k) > 1}
            if dup:
                offenders.append(f"{p}×{length}×{market}@{eps}: {sorted(dup)}")
    assert not offenders, f"beat キーの重複 {len(offenders)} 件:\n" + "\n".join(offenders[:20])
