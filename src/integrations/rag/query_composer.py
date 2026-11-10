"""Plan R5 C5: QueryComposer — 執筆コンテキストから検索クエリを合成 (LLM 0回・決定論).

プロット概要・シーン・アクティブキャラ名・前話末尾・契約/期限超過伏線キーワードから、
検索クエリ文字列と QueryReformulator 用キーワードリストを合成する。
従来の貧弱クエリ ``f"{character_name} ep{N}"`` を置換する。
"""

from __future__ import annotations

from typing import Any

from src.engine.nlp.japanese_tokenizer import JapaneseTokenizer

# 日本語の機能語・ストップワード。簡易リスト（形態素解析辞書に依存しない）。
_STOPWORDS = {
    "の","に","は","を","た","が","と","で","も","から","まで","へ","や","ね","よ",
    "あ","い","う","え","お","か","き","く","け","こ","さ","し","す","せ","そ",
    "ち","つ","て","と","な","に","ぬ","ね","の","は","ひ","ふ","へ","ほ",
    "ま","み","む","め","も","や","ゆ","よ","ら","り","る","れ","ろ","わ","を","ん",
    "について","そして","しかし","また","その","この","あの","どの","だ","である",
    "ます","ました","ない","いる","ある","です","だった","という","ため","により",
    "による","として","において","に関する","についての","など","より","までの",
}

_MAX_KEYWORDS = 8


class QueryComposer:
    """執筆コンテキストから検索クエリとキーワードを決定論的に合成する。"""

    def __init__(self, tokenizer: JapaneseTokenizer | None = None) -> None:
        self.tokenizer = tokenizer or JapaneseTokenizer()

    def compose_episode_query(
        self,
        *,
        plot_summary: str = "",
        scenes: list[Any] | None = None,
        character_names: list[str] | None = None,
        previous_tail: str = "",
        foreshadowing_keywords: list[str] | None = None,
        max_keywords: int = _MAX_KEYWORDS,
    ) -> dict[str, Any]:
        """検索クエリとキーワードを合成して返す。

        Returns:
            {"query": str, "keywords": list[str]}
        """
        scenes = scenes or []
        character_names = [n for n in (character_names or []) if n]
        foreshadowing_keywords = [k for k in (foreshadowing_keywords or []) if k]

        parts: list[str] = []
        if plot_summary and plot_summary.strip():
            parts.append(plot_summary.strip())
        for s in scenes[:3]:
            text = str(s or "").strip()
            if text:
                parts.append(text)
        if character_names:
            parts.append(" ".join(character_names))
        if previous_tail and previous_tail.strip():
            parts.append(previous_tail.strip()[-200:])

        query = "、".join(p for p in parts if p).strip() or "小説 設定 伏線"

        keywords: list[str] = []
        seen: set[str] = set()

        # 伏線キーワードを優先的に予約（上限まで）。plot トークンで枠を埋めてからでは
        # 伏線が入りきらないため、先に確保する。
        for k in foreshadowing_keywords:
            if len(keywords) >= max_keywords:
                break
            if k not in seen:
                seen.add(k)
                keywords.append(k)

        tokens = self.tokenizer.tokenize(query)
        for t in tokens:
            if len(keywords) >= max_keywords:
                break
            if t in _STOPWORDS or len(t) <= 1:
                continue
            if t in seen:
                continue
            seen.add(t)
            keywords.append(t)

        return {"query": query, "keywords": keywords}
