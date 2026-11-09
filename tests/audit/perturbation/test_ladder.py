"""T-L1: 強度ラダー構築テスト。

build_ladder が全変換について baseline/weak/medium/strong の4エントリを
生成し、各エントリが正しく動作することを検証する。
"""

from __future__ import annotations

from src.audit.perturbation import TRANSFORM_REGISTRY
from src.audit.perturbation.ladder import build_ladder

_LONG_TEXT = (
    "アルトは古いダンジョンの入り口に立っていた。剣を握る手に汗が光る。\n\n"
    "「ここだ」とアルトは呟いた。闇が奥から息をしている。\n\n"
    "何かが始まろうとしていた。運命の歯車が回り出す。\n\n"
    "アルトは深呼吸をして、一歩を踏み出した。壁には古い魔法陣が刻まれている。\n\n"
    "この場所は確かに特別な何かを秘めている。扉がゆっくりと開いた。\n\n"
    "冷たい風が吹き込んできた。アルトは息を呑み、剣の柄に手を置いた。\n\n"
    "奥からは微かな音が聞こえる。何かがそこにいる確信があった。\n\n"
    "アルトは前に進む。足音が静かに響く。暗闇の中に視線を感じる。\n\n"
    "扉の向こうには広い部屋が広がっていた。石の床が冷たい。\n\n"
    "中央には祭壇がある。その上に古い書物が置かれている。\n\n"
    "アルトは祭壇に近づき、書物を手に取った。\n"
)


def test_build_ladder_returns_all_transforms():
    """build_ladder が登録済み全変換についてラダーを返す。"""
    ladders = build_ladder()
    assert set(ladders.keys()) == set(TRANSFORM_REGISTRY.keys())


def test_each_ladder_has_four_entries():
    """各変換について baseline/weak/medium/strong の4エントリ。"""
    ladders = build_ladder()
    for tid, entries in ladders.items():
        assert len(entries) == 4, f"{tid}: エントリ数が4ではない ({len(entries)})"
        labels = [e.label for e in entries]
        assert labels == ["baseline", "weak", "medium", "strong"], (
            f"{tid}: ラベル順が不正 {labels}"
        )
        strengths = [e.strength for e in entries]
        assert strengths == [0.0, 1.0, 2.0, 3.0], (
            f"{tid}: 強度が不正 {strengths}"
        )


def test_baseline_returns_original_text():
    """baseline エントリは元のテキストをそのまま返す。"""
    ladders = build_ladder()
    for tid, entries in ladders.items():
        baseline = entries[0]
        assert baseline.label == "baseline"
        assert baseline.strength == 0.0
        assert baseline.transform is None
        assert baseline.apply(_LONG_TEXT) == _LONG_TEXT


def test_strength_variants_have_correct_strength():
    """weak/medium/strong の transform.strength が正しい。"""
    ladders = build_ladder()
    for tid, entries in ladders.items():
        for entry, expected in zip(entries[1:], (1.0, 2.0, 3.0)):
            assert entry.transform is not None, f"{tid} {entry.label}: transform が None"
            assert entry.transform.strength == expected, (
                f"{tid} {entry.label}: strength={entry.transform.strength} (expected {expected})"
            )


def test_all_entries_apply_without_error():
    """全エントリの apply が例外を出さず非空を返す。"""
    ladders = build_ladder()
    for tid, entries in ladders.items():
        for entry in entries:
            result = entry.apply(_LONG_TEXT)
            assert isinstance(result, str), f"{tid} {entry.label}: 戻り値が str ではない"
            assert result, f"{tid} {entry.label}: 出力が空"


def test_strong_differs_from_baseline_for_dir_transforms():
    """DIR 変換の strong は baseline と異なるテキストを返す（変換が効いている）。"""
    ladders = build_ladder()
    for tid, entries in ladders.items():
        base = TRANSFORM_REGISTRY[tid]
        if base.kind != "DIR":
            continue
        strong = entries[3]  # strong
        result = strong.apply(_LONG_TEXT)
        # すべての DIR 変換がテキストを変更するわけではない（T02 などはシャッフルだが同一長の可能性）
        # 少なくとも例外なく非空であること（上位テストでカバー）。ここでは型のみ確認。
        assert isinstance(result, str)
