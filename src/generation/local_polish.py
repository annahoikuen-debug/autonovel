"""
局所パッチ（Single-shot Polish） - 指摘された特定シーンのみの再生成
"""

import inspect
import logging
import re
from typing import Any, Tuple
from src.audit.unified_llm_auditor import call_llm_api

logger = logging.getLogger(__name__)


async def _generate(llm: Any, prompt: str) -> str:
    """注入 LLM を呼んでテキストを返す（async/sync どちらの llm にも対応）。"""
    for attr in ("generate_text", "generate"):
        fn = getattr(llm, attr, None)
        if fn is None:
            continue
        out = fn(prompt)
        if inspect.isawaitable(out):
            out = await out
        return out if isinstance(out, str) else str(out)
    raise TypeError(f"注入 LLM に generate_text / generate が無い: {type(llm)}")


def sanitize_polished_text(raw_text: str) -> str:
    """
    LLMが生成した推敲文から、AIアシスタントの定型前置きやおしゃべりを除去し、
    純粋な小説本文のみを抽出・サニタイズする。
    """
    if not raw_text:
        return ""

    text = raw_text.strip()

    # 1. コードブロックで囲まれている場合は中身を取り出す
    code_match = re.search(r"```(?:\w+)?\s*([\s\S]*?)\s*```", text)
    if code_match:
        text = code_match.group(1).strip()

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # 前置き判定キーワード
    preamble_keywords = ("承知", "了解", "かしこまりました", "修正後", "修正案", "改善後", "改善案", "推敲後", "以下")
    # 後書き判定キーワード
    postscript_keywords = ("以上", "ご参考", "お役に", "いかがでしょうか")

    # 先頭行が前置きなら除去
    while lines and any(kw in lines[0] for kw in preamble_keywords) and (
        "：" in lines[0] or ":" in lines[0] or "。" in lines[0] or len(lines[0]) < 40
    ):
        lines.pop(0)

    # 末尾行が後書きなら除去
    while lines and any(kw in lines[-1] for kw in postscript_keywords) and len(lines[-1]) < 50:
        lines.pop()

    result = "\n".join(lines).strip()

    # 全体を囲む余分なクォート（"...", 「...」）を、単一ブロックなら外す
    if (result.startswith("「") and result.endswith("」") and result.count("「") == 1) or \
       (result.startswith('"') and result.endswith('"') and result.count('"') == 2):
        result = result[1:-1].strip()

    return result


class LocalPolisher:
    """局所パッチを実行するクラス - 特定範囲のみのテキスト再生成"""

    def polish(self, text: str, target_range: Tuple[int, int], improvement_instruction: str) -> str:
        """
        指定された範囲のテキストのみを改善（局所パッチ）

        同期版。LLM 呼び出しはモジュールグローバル ``call_llm_api`` を使う。
        T6 Step 7 以降、本番経路では ``polish_with_llm()`` が使われ、
        注入された（計測可能な）LLM を経由する。この版は
        後方互換のため残している。

        Args:
            text: 元のテキスト
            target_range: (start_index, end_index) - 改善対象の範囲（end_indexは排他的）
            improvement_instruction: 改善のための指示（例: "より感情豊かに書き直して"）

        Returns:
            str: 局所パッチ適用後のテキスト
        """
        start_idx, end_idx = target_range
        if start_idx < 0 or end_idx > len(text) or start_idx >= end_idx:
            return text
        try:
            improved_text = call_llm_api(
                self._build_prompt(text, target_range, improvement_instruction)
            )
        except Exception:
            # LLM呼び出しに失敗した場合は元のテキストを返す
            logger.warning("局所パッチの LLM 呼び出しに失敗しました", exc_info=True)
            return text
        return self._apply(text, target_range, improved_text)

    async def polish_with_llm(
        self,
        text: str,
        target_range: Tuple[int, int],
        improvement_instruction: str,
        llm: Any,
    ) -> str:
        """注入された LLM で局所パッチを適用する（T6 Step 7）。

        旧実装はモジュールグローバル ``call_llm_api`` を直接呼ぶため、
        ``tracked_adapter``（token/cost 計測付き）を**バイパス**していた。
        結果として、この経路の LLM コストは計測に一切乗っていなかった。
        """
        start_idx, end_idx = target_range
        # 範囲が不正なら LLM を呼ばない（無駄なコストを避ける）
        if start_idx < 0 or end_idx > len(text) or start_idx >= end_idx:
            return text
        prompt = self._build_prompt(text, target_range, improvement_instruction)
        improved_text = await _generate(llm, prompt)
        return self._apply(text, target_range, improved_text)

    def _build_prompt(
        self, text: str, target_range: Tuple[int, int], improvement_instruction: str
    ) -> str:
        """対象範囲・前後文脈・指示からプロンプトを組み立てる。"""
        start_idx, end_idx = target_range
        if start_idx < 0 or end_idx > len(text) or start_idx >= end_idx:
            return ""
        target_text = text[start_idx:end_idx]
        context_start = max(0, start_idx - 50)
        before_context = text[context_start:start_idx]
        context_end = min(len(text), end_idx + 50)
        after_context = text[end_idx:context_end]
        return self._create_polish_prompt(
            before_context, target_text, after_context, improvement_instruction
        )

    def _apply(
        self, text: str, target_range: Tuple[int, int], improved_text: str
    ) -> str:
        """生成結果をサニタイズして原文へ組み込む。失敗時は原文を返す。"""
        start_idx, end_idx = target_range
        if start_idx < 0 or end_idx > len(text) or start_idx >= end_idx:
            return text
        try:
            sanitized = sanitize_polished_text(improved_text or "")
            if not sanitized:
                return text
            return text[:start_idx] + sanitized + text[end_idx:]
        except Exception:
            logger.warning("局所パッチの適用に失敗しました", exc_info=True)
            return text

    def _create_polish_prompt(self, before_context: str, target_text: str,
                            after_context: str, improvement_instruction: str) -> str:
        """
        局所パッチ用のプロンプトを構築
        """
        prompt = f"""
あなたは小説の執筆を補助する専門編集アシスタントです。
以下の文脈を考慮して、指定された範囲のテキストを改善してください。

前方文脈：
{before_context}

対象範囲：
{target_text}

後方文脈：
{after_context}

改善指示：
{improvement_instruction}

上記の文脈と改善指示を考慮して、対象範囲のテキストを改善してください。
改善後のテキストのみを返してください（前方文脈と後方文脈は含めないでください）。
"""
        return prompt.strip()
