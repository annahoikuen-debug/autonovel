"""全組合せの網羅テスト。1つも崩れていてはいけない。"""

import itertools

from config.story_spine import LENGTHS, MARKETS, PATTERNS, resolve_spine


def test_full_combinatorial_matrix_never_raises():
    """38パターン × 6長さ × 4媒体 × 3話数 = 2,736 ケース。"""
    count = 0
    for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
        lo, hi = LENGTHS[l]["eps_range"]
        for eps in (lo, (lo + hi) // 2, hi):
            spine = resolve_spine(p, l, m, eps)
            assert spine.beats, f"{p}×{l}×{m}@{eps} が空"
            count += 1
    assert count == 38 * 6 * 4 * 3, f"ケース数が {count}（2736 のはず）"


def test_every_beat_is_backed_by_known_vocabulary():
    from config.story_spine import BEAT_VOCABULARY

    for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
        lo, hi = LENGTHS[l]["eps_range"]
        for b in resolve_spine(p, l, m, lo).beats:
            assert b.key in BEAT_VOCABULARY, f"{p}: 未知 beat {b.key!r}"


def test_every_episode_is_covered():
    """1話から total_eps まで、どの話にも必ず beat が割り当てられていること。"""
    for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
        lo, hi = LENGTHS[l]["eps_range"]
        eps = hi
        spine = resolve_spine(p, l, m, eps)
        for ep in range(1, eps + 1):
            assert spine.at(ep) is not None, f"{p}×{l}×{m}@{eps}: 第{ep}話に beat が無い"


def test_episode_ranges_stay_within_bounds():
    for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
        lo, hi = LENGTHS[l]["eps_range"]
        eps = hi
        spine = resolve_spine(p, l, m, eps)
        for b in spine.beats:
            assert 1 <= b.ep_start <= b.ep_end <= eps, (
                f"{p}×{l}×{m}@{eps}: {b.key} の範囲が不正 {b.ep_start}-{b.ep_end}"
            )


def test_duty_stays_within_60_chars_after_merging():
    """統合済み duty も語彙の約束（60字以内）を守る。"""
    for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
        lo, hi = LENGTHS[l]["eps_range"]
        for b in resolve_spine(p, l, m, lo).beats:
            assert len(b.duty) <= 60, f"{p}: {b.key} の duty が {len(b.duty)}字"
            assert b.duty.endswith("。"), f"{p}: {b.key} の duty が句点で終わっていない"


def test_unknown_keys_fall_back_instead_of_raising():
    """未知キーで例外を投げないこと（B の12ステップを壊さないため）。"""
    for args in (
        ("nope", "short", "general", 3),
        ("exile_rise", "nope", "general", 3),
        ("exile_rise", "short", "nope", 3),
    ):
        assert resolve_spine(*args).beats


def test_total_eps_of_one_is_never_an_error():
    """話数 1 でも必ず1つ以上の beat を返す。"""
    for p in PATTERNS:
        for m in MARKETS:
            assert resolve_spine(p, "short", m, 1).beats


def test_resolve_spine_is_fast_enough_for_ui():
    """カード選択で同期呼出しされるため、1件あたり数十 ms で済むこと。"""
    import time

    start = time.perf_counter()
    for p in PATTERNS:
        resolve_spine(p, "web_volume", "web", 40)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"38パターンの解決に {elapsed:.2f}s かかっている"
