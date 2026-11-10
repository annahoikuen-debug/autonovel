"""
H8: 検証付き quote（逐語引用）置換コア。

監査が提示する「修正前 quote / 修正後 replacement」を本文に対して
検証付きで置換する。**LLM を 1 回も呼ばない純関数**であり、
ネットワーク・DB も使わない。置換結果は `SpanPatchApplier.validate`
（長さ比 0.3-3.0 倍・段落数減少禁止）を通過しない限り本文に反映されず、
原文は一切破壊されない。

「追記型パッチ（末尾に講評的文面を追加する方式）」を廃止し、
置換型に統一することで文脈矛盾の残留を防ぐ。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from src.engine.prose.span_patch_applier import SpanPatchApplier


@dataclass(frozen=True)
class QuotePatch:
    """1 件の quote → replacement 置換指示。"""

    original_quote: str   # 本文中に実在する断片（逐語引用）
    replacement: str      # 差し替え文
    rationale: str = ""   # 書き換え理由（ログ・教訓用。置換には影響しない）


@dataclass(frozen=True)
class QuotePatchResult:
    """apply_quote_patches の結果。"""

    text: str                       # 置換後本文（不採用の場合は原文と同一）
    applied_count: int              # 採用された置換件数
    rejected: tuple[QuotePatch, ...]  # 未発見・検証不通で採用されなかった置換


def _normalize_ws(text: str) -> str:
    """空白（半角/全角スペース・タブ・改行）を 1 個の半角スペースに集約し、
    前後の空白を削除した正規化文字列を返す。"""
    return re.sub(r"\s+", " ", text).strip()


def _build_norm_map(text: str) -> tuple[str, list[int]]:
    """空白を圧縮した正規化テキストと、各正規化文字が元テキストの
    何番目のインデックスに対応するかの対応リストを返す。

    戻り値 `(norm_text, orig_indices)` では `orig_indices[k]` が
    `norm_text[k]` の元テキスト上のインデックスとなる（空白を含む）。
    これにより、正規化テキスト上のスパンを元テキストのスパンに
    逆変換できる。
    """
    norm_chars: list[str] = []
    orig_indices: list[int] = []
    prev_was_space = True  # 先頭の空白は圧縮で除去するため True で初期化
    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_was_space:
                # 連続空白を 1 つの半角スペースに圧縮（最初の空白の位置を代表とする）
                norm_chars.append(" ")
                orig_indices.append(i)
            prev_was_space = True
        else:
            norm_chars.append(ch)
            orig_indices.append(i)
            prev_was_space = False
    return "".join(norm_chars), orig_indices


def find_quote_span(
    text: str,
    quote: str,
    *,
    max_quote_chars: int,
) -> tuple[int, int] | None:
    """quote の本文内スパン（開始インデックス[含む), 終了インデックス[除く)）を返す。

    - quote が空文字、または max_quote_chars を超える場合は None。
    - 逐語一致を優先し、見つからなければ空白正規化後の一致を試す。
    - 複数出現する場合は**最初の出現**のみを返す。
    - 一致しなければ None。

    戻り値のスパンは元の `text` に対するインデックスなので、
    そのまま `text[start:end]` で quote 本体を抽出できる。
    """
    if not quote or not quote.strip():
        return None
    if len(quote) > max_quote_chars:
        return None

    # 1. 逐語一致（最優先：置換後の位置ずれを避けるため）
    start = text.find(quote)
    if start != -1:
        return (start, start + len(quote))

    # 2. 空白正規化一致（全角/半角スペース・改行の揺れを吸収）。
    quote_norm = _normalize_ws(quote)
    if not quote_norm:
        return None

    text_norm, orig_indices = _build_norm_map(text)
    norm_start = text_norm.find(quote_norm)
    if norm_start == -1:
        return None

    quote_len_norm = len(quote_norm)
    last_norm_idx = norm_start + quote_len_norm - 1
    if last_norm_idx >= len(orig_indices):
        return None
    orig_start = orig_indices[norm_start]
    orig_end = orig_indices[last_norm_idx] + 1
    return (orig_start, orig_end)


def apply_quote_patches(
    text: str,
    patches: Sequence[QuotePatch],
    *,
    max_patches: int = 3,
) -> QuotePatchResult:
    """複数の QuotePatch を本文に順次適用する。

    各パッチについて find_quote_span でスパンを特定し、
    SpanPatchApplier().apply で置換を試行。検証不通・未発見は rejected に回収し、
    原文は破壊しない。適用可能なパッチは max_patches 件まで。

    LLM を 1 回も呼ばない純関数。

    Args:
        text: 対象の本文
        patches: 置換指示の列（適用順に並べることを推奨）
        max_patches: 1 回の呼び出しで採用する最大件数

    Returns:
        QuotePatchResult（text は常に str で、未採用時は原文と同一）
    """
    if not isinstance(text, str):
        return QuotePatchResult(text="", applied_count=0, rejected=tuple(patches))

    current = text
    rejected: list[QuotePatch] = []
    applied_count = 0
    applier = SpanPatchApplier()

    for patch in patches:
        if applied_count >= max_patches:
            rejected.append(patch)
            continue

        quote = patch.original_quote
        if not quote or not quote.strip() or len(quote) > 400:
            rejected.append(patch)
            continue

        span = find_quote_span(current, quote, max_quote_chars=400)
        if span is None:
            rejected.append(patch)
            continue

        start, end = span
        patched, ok = applier.apply(current, start, end, patch.replacement)
        if not ok or patched == current:
            rejected.append(patch)
            continue

        current = patched
        applied_count += 1

    return QuotePatchResult(text=current, applied_count=applied_count, rejected=tuple(rejected))


__all__ = [
    "QuotePatch",
    "QuotePatchResult",
    "find_quote_span",
    "apply_quote_patches",
]
