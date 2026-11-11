"""階層的ダイジェストロールアップ生成器 (PLAN_M1 Step 6).

メンバの1話ダイジェストから章(ブロック)要約を生成し、章要約から巻要約を
生成する。LLM は tier1 軽量モデルを想定し、fail-open（失敗しても例外を
出さず warning のみ）で動作する。

`digest_service.py` の `generate_episode_digest` と同じ LLM 呼び出しパターン
(generate / ainvoke / predict / callable) に合わせる。
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("rollup_generator")


def _is_awaitable(obj: Any) -> bool:
    return inspect.isawaitable(obj)


def _extract_text(res: Any) -> str:
    if isinstance(res, str):
        return res
    if hasattr(res, "text"):
        return str(res.text)
    if hasattr(res, "content"):
        return str(res.content)
    if isinstance(res, dict) and "content" in res:
        return str(res["content"])
    return str(res)


class RollupGenerator:
    """章/巻ロールアップの生成器。"""

    def __init__(self, cfg: Any, llm: Any = None):
        """Args:
            cfg: RollupConfig 互換オブジェクト（episodes_per_block,
                blocks_per_volume, block_digest_chars, volume_digest_chars,
                cod_rounds を持つ）。
            llm: LLM クライアント（None でも fail-open で動作）。
        """
        self.cfg = cfg
        self.llm = llm

    # ── 境界判定 ──────────────────────────────────────────────

    def should_generate_block(self, ep_num: int) -> bool:
        """ep_num が章(ブロック)境界か。"""
        return ep_num % self.cfg.episodes_per_block == 0

    def should_generate_volume(self, ep_num: int) -> bool:
        """ep_num が巻境界か。"""
        block_per_volume = self.cfg.episodes_per_block * self.cfg.blocks_per_volume
        return ep_num % block_per_volume == 0

    # ── LLM 呼び出し（digest_service と同じパターン）──────────

    async def _call_llm(self, prompt: str) -> str:
        """LLM を呼び出してテキストを取得する。失敗時は空文字。"""
        if self.llm is None:
            return ""
        try:
            if hasattr(self.llm, "generate"):
                res = self.llm.generate(prompt=prompt, temperature=0.1)
                if _is_awaitable(res):
                    res = await res
                return _extract_text(res)
            if hasattr(self.llm, "ainvoke"):
                res = await self.llm.ainvoke(prompt)
                return _extract_text(res)
            if hasattr(self.llm, "predict"):
                res = self.llm.predict(prompt)
                if _is_awaitable(res):
                    res = await res
                return str(res)
            if callable(self.llm):
                res = self.llm(prompt)
                if _is_awaitable(res):
                    res = await res
                return str(res)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Rollup LLM generation failed: {e}")
        return ""

    # ── 章ロールアップ生成 ──────────────────────────────────

    async def generate_block_rollup(
        self,
        book_id: int,
        ep_range: Tuple[int, int],
        member_digests: Dict[int, str],
        llm: Any = None,
        cod_rounds: Optional[int] = None,
    ) -> Optional[str]:
        """メンバの1話ダイジェストから章要約を生成（≤ block_digest_chars 字）。

        Returns:
            章要約テキスト。LLM 未設定・失敗時は None。

        Chain-of-Density (CoD):
            cod_rounds=1 で現行の 1 pass と同一。
            cod_rounds>=2 で、1 pass 目の要約を入力としてさらに圧縮するパスを
            (cod_rounds-1) 回追加し、情報密度を高める。
        """
        effective_llm = llm or self.llm
        rounds = cod_rounds if cod_rounds is not None else self.cfg.cod_rounds
        if not member_digests or effective_llm is None:
            return None

        original_llm = self.llm
        self.llm = effective_llm
        try:
            lines = [
                f"第{ep}話: {text}" for ep, text in sorted(member_digests.items())
            ]
            joined = "\n".join(lines)
            prompt = (
                f"以下は第{ep_range[0]}話〜第{ep_range[1]}話の確定事実ダイジェストです。\n"
                f"これらを統合して、この章(ブロック)の確定事実要約を"
                f"{self.cfg.block_digest_chars}字以内で日本語で作成してください。\n"
                f"感情や修飾語は省き、客観的な出来事（行動・獲得・変化）のみを記述せよ。\n\n"
                f"【確定事実ダイジェスト一覧】\n{joined}\n\n"
                f"【章要約（{self.cfg.block_digest_chars}字以内）】"
            )
            digest_text = await self._call_llm(prompt)

            # CoD 2 回目以降: 既存要約をさらに圧縮して密度を高める
            for _ in range(max(0, rounds - 1)):
                if not digest_text or not digest_text.strip():
                    break
                compress_prompt = (
                    f"以下は既に要約されたテキストです。\n"
                    f"冗長な表現や接続詞を省き、情報密度を高めて、"
                    f"{self.cfg.block_digest_chars}字以内で日本語に圧縮してください。\n\n"
                    f"【要約テキスト】\n{digest_text}\n\n"
                    f"【圧縮要約（{self.cfg.block_digest_chars}字以内）】"
                )
                digest_text = await self._call_llm(compress_prompt)
        finally:
            self.llm = original_llm

        if not digest_text or not digest_text.strip():
            return None

        # 文字数クランプ
        if len(digest_text) > self.cfg.block_digest_chars:
            digest_text = digest_text[: self.cfg.block_digest_chars - 3].rstrip() + "..."
        return digest_text

    async def generate_volume_rollup(
        self,
        book_id: int,
        block_rollups: List[Tuple[int, int, str]],
        llm: Any = None,
        cod_rounds: Optional[int] = None,
    ) -> Optional[str]:
        """章ロールアップから巻要約を生成（≤ volume_digest_chars 字）。

        `block_rollups` は (start_ep, end_ep, digest_text) のリスト。

        Chain-of-Density (CoD):
            cod_rounds=1 で現行の 1 pass と同一。
            cod_rounds>=2 で、1 pass 目の要約を入力としてさらに圧縮するパスを
            (cod_rounds-1) 回追加し、情報密度を高める。
        """
        effective_llm = llm or self.llm
        rounds = cod_rounds if cod_rounds is not None else self.cfg.cod_rounds
        if not block_rollups or effective_llm is None:
            return None

        original_llm = self.llm
        self.llm = effective_llm
        try:
            lines = [
                f"第{start}話〜第{end}話: {text}" for start, end, text in block_rollups
            ]
            joined = "\n".join(lines)
            prompt = (
                f"以下は複数の章の確定事実要約です。\n"
                f"これらを統合して、この巻の確定事実要約を"
                f"{self.cfg.volume_digest_chars}字以内で日本語で作成してください。\n"
                f"感情や修飾語は省き、客観的な出来事のみを記述せよ。\n\n"
                f"【章要約一覧】\n{joined}\n\n"
                f"【巻要約（{self.cfg.volume_digest_chars}字以内）】"
            )
            digest_text = await self._call_llm(prompt)

            # CoD 2 回目以降: 既存要約をさらに圧縮して密度を高める
            for _ in range(max(0, rounds - 1)):
                if not digest_text or not digest_text.strip():
                    break
                compress_prompt = (
                    f"以下は既に要約されたテキストです。\n"
                    f"冗長な表現や接続詞を省き、情報密度を高めて、"
                    f"{self.cfg.volume_digest_chars}字以内で日本語に圧縮してください。\n\n"
                    f"【要約テキスト】\n{digest_text}\n\n"
                    f"【圧縮要約（{self.cfg.volume_digest_chars}字以内）】"
                )
                digest_text = await self._call_llm(compress_prompt)
        finally:
            self.llm = original_llm

        if not digest_text or not digest_text.strip():
            return None

        if len(digest_text) > self.cfg.volume_digest_chars:
            digest_text = digest_text[: self.cfg.volume_digest_chars - 3].rstrip() + "..."
        return digest_text
