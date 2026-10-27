"""ナラティブアンカーとビート区間の正規化（PLAN_W5_CAUSAL_FORESIGHT_12STEPS Step 2）。

## なぜ要るのか（W5-04）

```
src/config/commercial_beat_sheet.py:61  get_beat_for_episode  ← 両端含む
src/services/foreshadowing/planner.py:80  start_ep <= ep < end_ep  ← 半開区間
```

**同じ `range` 型が 2 つの意味で使われていた**ため、境界話（例: 第10話）で
「`get_beat_for_episode` は (4,10) を返すのに `_next_payoff_beat` は (11,18) を探す」
というズレが起きうる。

本モジュールは **伏線パッケージ内の唯一の解釈**を固定する。既存の
`get_beat_for_episode` は変更しない（本パッケージ内からそれを使わないだけ）。

## 半開区間の境界の扱い

`range` は `start <= ep < end`（半開）を正とする。この解釈だと各ビートの
**終了話 itself**（3 / 10 / 18 / 25 / 32 / 38 / 40）がどのビートにも属さない。
そのため境界話には「**次のビート**」（無ければ最後のビート）を割り当てる。
これが「(4,10) の半開区間なので第10話は (11,18) に属する」という解釈である。
"""

from __future__ import annotations

from src.config.commercial_beat_sheet import COMMERCIAL_40EP_BEATS

#: 本パッケージ内の唯一の解釈。`range` は `start <= ep < end`（半開区間）。
BEAT_RANGE_IS_HALF_OPEN = True

#: 物語の節目アンカー名（`COMMERCIAL_40EP_BEATS` の phase 列に対応）。
ANCHOR_NAMES = ("opening", "first_trial", "midpoint", "crisis", "climax", "resolution")

#: 長期伏線を吸着させる節目。
PAYOFF_ANCHORS = ("midpoint", "climax", "resolution")

#: アンカー名 → phase 文字列のキーワード（英字は小文字で照合する）。
_ANCHOR_PHASE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "opening": ("開幕",),
    "first_trial": ("第1の試練", "試練"),
    "midpoint": ("midpoint",),
    "crisis": ("最大の危機", "危機"),
    "climax": ("クライマックス",),
    "resolution": ("凱旋",),
}

#: range 昇順に並べたビート表（1度だけソートする）。
_SORTED_BEATS = sorted(COMMERCIAL_40EP_BEATS, key=lambda b: b["range"][0])


def beat_for_episode(ep: int) -> dict:
    """話数に対応するビートを **半開区間** で返す。

    既存 `get_beat_for_episode` と違い、要素をそのまま返す（新しい dict を作らない）。

    Args:
        ep: 話数（1-indexed）

    Returns:
        `COMMERCIAL_40EP_BEATS` の要素。範囲外は最後のビート。
    """
    try:
        ep = int(ep)
    except (TypeError, ValueError):
        return _SORTED_BEATS[-1]

    for beat in _SORTED_BEATS:
        start_ep, end_ep = beat["range"]
        if start_ep <= ep < end_ep:
            return beat

    # 半開区間に取りこぼした境界話（(4,10) の 10 など）は「次のビート」に属する
    for beat in _SORTED_BEATS:
        if beat["range"][0] > ep:
            return beat

    # 最終話を超える場合は最後のビート（既存 API と同じフォールバック）
    return _SORTED_BEATS[-1]


def anchor_episode(anchor: str) -> int:
    """アンカー名から**代表話**（そのビート区間の開始話）を返す。

    未知のアンカー名は例外を送出せず、最後のビート開始話（= `COMMERCIAL_40EP_BEATS`
    の終端）を返す。
    """
    keywords = _ANCHOR_PHASE_KEYWORDS.get(anchor)
    if keywords:
        for beat in _SORTED_BEATS:
            phase = str(beat.get("phase", "")).lower()
            if any(k.lower() in phase for k in keywords):
                return beat["range"][0]
    return _SORTED_BEATS[-1]["range"][0]


def is_anchor_episode(ep: int, anchors: tuple[str, ...] = PAYOFF_ANCHORS) -> bool:
    """その話数がアンカー話（既定は回収節目）かどうかを判定する。"""
    try:
        ep = int(ep)
    except (TypeError, ValueError):
        return False
    return any(ep == anchor_episode(a) for a in anchors)
