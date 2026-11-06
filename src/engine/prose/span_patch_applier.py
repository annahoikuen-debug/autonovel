"""
決定論的スパン置換（W4 Step 5）。

`LocalPolisher._apply` は結果を無検証に本文へ埋め込むため、
「元の1段落が10分の1に縮んだ」「段落が3つ潰れた」ような壊れ方が素通しで確定する。
ここでは LLM・ネットワーク・DB を使わない純粋クラスとして、
差し替え結果の安全条件を機械的に検証する。
"""

from __future__ import annotations

# 段落区切り（改行1つは段落分割に使わないため数えない）
_PARAGRAPH_SEP = "\n\n"
# 差し替え後の本文長の許容比（min/max）
_MIN_LENGTH_RATIO = 0.3
_MAX_LENGTH_RATIO = 3.0


class SpanPatchApplier:
    """スパン置換の安全条件を検査する純クラス（例外を送出しない）。"""

    def apply(
        self, text: str, start: int, end: int, replacement: str
    ) -> tuple[str, bool]:
        """スパン置換を行い、安全条件を満たした場合だけ新しいテキストを返す。

        Returns:
            (置換後のテキスト or 原文, 採用したか)
        """
        try:
            if not isinstance(text, str) or not isinstance(replacement, str):
                return (text, False)
            if not isinstance(start, int) or not isinstance(end, int):
                return (text, False)
            # 範囲の妥当性（0 <= start < end <= len(text)）
            if not (0 <= start < end <= len(text)):
                return (text, False)
            # 空の差し替えは破壊なので弾く
            if not replacement.strip():
                return (text, False)
            patched = text[:start] + replacement + text[end:]
            if not self.validate(text, patched):
                return (text, False)
            return (patched, True)
        except Exception:
            return (text, False)

    def validate(self, original: str, patched: str) -> bool:
        """差し替え後の本文が壊れていないかを判定する（LLM は呼ばない）。

        - 差し替え後が空でない
        - 長さが元の 0.3 倍以上 3.0 倍以下
        - 段落数が減っていない（``\\n\\n`` の個数比較）
        """
        try:
            if not isinstance(original, str) or not isinstance(patched, str):
                return False
            if not patched.strip():
                return False
            if not (
                len(original) * _MIN_LENGTH_RATIO
                <= len(patched)
                <= len(original) * _MAX_LENGTH_RATIO
            ):
                return False
            if patched.count(_PARAGRAPH_SEP) < original.count(_PARAGRAPH_SEP):
                return False
            return True
        except Exception:
            return False
