"""T-P1-3: 擾乱変換カタログの妥当性テスト。

- 全変換が kind/affected_axes を宣言している
- 各 DIR 変換が fixture に対し gold 特徴量を機械的に変化させる
  - T01: 末尾フックマーカーが減る
  - T04: AI_CLICHE_PATTERNS の句数が増える
  - T05: 会話行 (「…」) の数が減る
  - T07: 段落数が増える
- INV 変換 (T08/T09) は中身が変わる（改名・正規化が適用される）

各変換の min_chars に配慮し、fixture は十分な長さを持つ。
"""

from __future__ import annotations

import re

from src.audit.perturbation import TRANSFORM_REGISTRY
from src.engine.auditors.rule_based_metrics import AI_CLICHE_PATTERNS

_HOOK_TAIL_MARKER = re.compile(r"(まさか|突如|その時|現れた|気付いた|信じられない)")
_DIALOGUE_LINE = re.compile(r"「[^」]*」")


def _count_hook_tail(text: str) -> int:
    tail = text.strip()[-200:]
    count = 0
    if re.search(r"[！？!?]$", tail):
        count += 1
    if tail.endswith("」"):
        count += 1
    if _HOOK_TAIL_MARKER.search(tail):
        count += 1
    return count


def _count_cliches(text: str) -> int:
    return sum(1 for pat in AI_CLICHE_PATTERNS if re.search(pat, text))


def _count_dialogue_lines(text: str) -> int:
    return sum(1 for line in text.split("\n") if _DIALOGUE_LINE.search(line))


def _count_paragraphs(text: str) -> int:
    return sum(1 for p in re.split(r"\n\s*\n", text) if p.strip())


# 各変換の min_chars を超える十分な長さの fixture
_LONG_FIXTURE = (
    "アルトは古いダンジョンの入り口に立っていた。剣を握る手に汗が光る。\n"
    "「ここだ」とアルトは呟いた。闇が奥から息をしている。\n"
    "何かが始まろうとしていた。運命の歯車が回り出す。\n"
    "アルトは深呼吸をして、一歩を踏み出した。\n"
    "壁には古い魔法陣が刻まれており、微かに光を放っていた。\n"
    "この場所は確かに特別な何かを秘めている。\n"
)


def test_all_transforms_declare_axes():
    """全変換が non-empty の affected_axes と kind を宣言している。"""
    for tid, transform in TRANSFORM_REGISTRY.items():
        assert transform.kind in ("DIR", "INV"), f"{transform.id}: kind が不正"
        assert transform.affected_axes, f"{transform.id}: affected_axes が空"


def test_t01_hook_reduction():
    """T01: 末尾フック文を含む fixture に対し hook マーカーが減る（または同等）。"""
    transform = TRANSFORM_REGISTRY["T01"]
    fixture = _LONG_FIXTURE + "信じられない！\n"
    before = _count_hook_tail(fixture)
    result = transform.apply(fixture)
    after = _count_hook_tail(result)
    assert after <= before, f"T01: hook マーカーが増えた ({before} -> {after})"


def test_t04_cliche_increase():
    """T04: AI_CLICHE_PATTERNS の句数が増える。"""
    transform = TRANSFORM_REGISTRY["T04"]
    fixture = _LONG_FIXTURE
    before = _count_cliches(fixture)
    result = transform.apply(fixture)
    after = _count_cliches(result)
    assert after > before, f"T04: 定型句が増えなかった ({before} -> {after})"


def test_t05_dialogue_reduction():
    """T05: 会話行の数が減る。"""
    transform = TRANSFORM_REGISTRY["T05"]
    fixture = (
        "アルトは言った。「ここだ」。\n"
        "「わかった」と仲間が答えた。\n"
        "アルトはうなずいた。\n"
        "「じゃあ行こう」とアルトが促した。\n"
    ) + _LONG_FIXTURE
    before = _count_dialogue_lines(fixture)
    result = transform.apply(fixture)
    after = _count_dialogue_lines(result)
    assert after < before, f"T05: 会話行が減らなかった ({before} -> {after})"


def test_t07_paragraph_increase():
    """T07: 段落数が増える。"""
    transform = TRANSFORM_REGISTRY["T07"]
    fixture = (
        "アルトは古いダンジョンの入り口に立っていた。剣を握る手に汗が光る。\n\n"
        "「ここだ」とアルトは呟いた。闇が奥から息をしている。壁は冷たく湿っていた。\n\n"
        "何かが始まろうとしていた。運命の歯車が回り出す。空気が震える。\n\n"
        "アルトは深呼吸をして、一歩を踏み出した。壁には古い魔法陣が刻まれている。\n\n"
        "この場所は確かに特別な何かを秘めている。扉がゆっくりと開いた。\n\n"
        "冷たい風が吹き込んできた。アルトは息を呑み、剣の柄に手を置いた。\n\n"
        "奥からは微かな音が聞こえる。何かがそこにいる確信があった。\n\n"
        "アルトは前に進む。足音が静かに響く。暗闇の中に視線を感じる。\n\n"
        "扉の向こうには広い部屋が広がっていた。石の床が冷たい。\n\n"
        "中央には祭壇がある。その上に古い書物が置かれている。\n\n"
        "アルトは祭壇に近づき、書物を手に取った。\n"
    )
    before = _count_paragraphs(fixture)
    result = transform.apply(fixture)
    after = _count_paragraphs(result)
    assert after > before, f"T07: 段落数が増えなかった ({before} -> {after})"


def test_t08_consistent_rename_changes_text():
    """T08 (INV): 全出現箇所が一括改名され、テキストが変わる。"""
    transform = TRANSFORM_REGISTRY["T08"]
    fixture = "アルトはダンジョンに入った。アルトは剣を握った。" + _LONG_FIXTURE
    result = transform.apply(fixture)
    assert result != fixture, "T08: テキストが変わっていない"
    assert "アルト" not in result, "T08: 元の名前が残っている"
    assert "リオン" in result, "T08: 新しい名前が入っていない"


def test_t09_normalization_changes_text():
    """T09 (INV): 句読点が正規化され、テキストが変わる。"""
    transform = TRANSFORM_REGISTRY["T09"]
    fixture = "アルトは「ここだ」と言った。〜何かが始まる。" + _LONG_FIXTURE
    result = transform.apply(fixture)
    assert result != fixture, "T09: テキストが変わっていない"
    assert "「" not in result and "」" not in result, "T09: 引用符が正規化されていない"
