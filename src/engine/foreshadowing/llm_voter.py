"""PLAN_S1 P1: 伏線回収判定の LLM 第 4 投票 (ForeshadowingLLMVoter)。

現行の ``EnsembleJudge`` は「執筆メタデータ自己申告 (40pt) + 契約 (35pt) + 構文解析 (25pt)」
の LLM 0 回投票であり、自己申告だけで RESOLVED 閾値 (75pt) に到達できる
(G-3)。本モジュールは本文と伏線情報を LLM に見せた第 4 票を提供する。

設計拘束 (PLAN_S1 §2):
- **P1 既定 off**: ``ENABLE_FORESHADOW_LLM_VOTE`` 未設定では一切呼ばれない。
- **P3 fail-open**: 例外・不正 JSON・タイムアウトは **None 投票** (fail-closed にしない。
  回収判定は監査ゲートではなく補完情報のため)。
- **マスキング**: プロンプトに model 名・provider 痕跡・出力元を含まない
  (改善 #9 ``judge_panel._build_judge_prompt`` と同一方針)。
- **コスト上限**: 本文はキーワード前後 ±500 字ウィンドウ・全体 ≤ 3000 字に圧縮。
  temp 0.2・tier1 軽量モデル。
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from typing import Any, Literal, Optional, Sequence, cast

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# コスト上限 (PLAN_S1 P1 / Q8 契約)
EXCERPT_WINDOW_CHARS = 500
EXCERPT_MAX_CHARS = 3000
VOTE_TEMPERATURE = 0.2

VoteAction = Literal["resolved", "progressed", "unmentioned"]
_VALID_ACTIONS = ("resolved", "progressed", "unmentioned")


class LLMVoteResult(BaseModel):
    """LLM 第 4 票の結果。失敗時は生成されない (None 投票)。"""

    foreshadowing_id: int
    action: VoteAction
    evidence_quote: str = Field(default="", max_length=120)
    raw_response: str = Field(default="", max_length=500)


def build_windowed_excerpt(
    draft_text: str,
    keywords: Sequence[str],
    window: int = EXCERPT_WINDOW_CHARS,
    max_chars: int = EXCERPT_MAX_CHARS,
) -> str:
    """キーワード出現位置の前後 ±window 字を結合した抜粋を作る (コスト上限)。

    - 本文全体が max_chars 以下ならそのまま返す
    - キーワードが 1 つも見つからない場合は先頭 max_chars 字
    - 隣接するウィンドウはマージし、予算を超えたら打ち切る
    """
    text = draft_text or ""
    if len(text) <= max_chars:
        return text

    positions = sorted({pos for kw in keywords if kw for pos in _find_all(text, kw)})
    if not positions:
        return text[:max_chars]

    # 隣接ウィンドウのマージ
    merged: list[list[int]] = []
    for pos in positions:
        start = max(0, pos - window)
        end = min(len(text), pos + window)
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    # 予算内で結合 (区切り文字 "\n…\n" (3字/セッション) も予算に含める)
    segments: list[str] = []
    total = 0
    for index, (start, end) in enumerate(merged):
        segment = text[start:end]
        overhead = 3 if index > 0 else 0  # 区切り文字
        allowed = max_chars - total - overhead
        if allowed <= 0:
            break
        if len(segment) > allowed:
            segment = segment[:allowed]
        segments.append(segment)
        total += overhead + len(segment)
    return "\n…\n".join(segments)


def _find_all(text: str, keyword: str, limit: int = 5) -> list[int]:
    """キーワードの出現位置を最大 limit 件返す。"""
    if not keyword:
        return []
    positions: list[int] = []
    start = 0
    while len(positions) < limit:
        pos = text.find(keyword, start)
        if pos < 0:
            break
        positions.append(pos)
        start = pos + len(keyword)
    return positions


class ForeshadowingLLMVoter:
    """伏線 1 本あたり 1 回の軽量 LLM 判定 (第 4 票)。

    ``llm`` は ``generate(prompt=..., temperature=...)`` を持つ duck-typed クライアント
    (``digest_service.generate_episode_digest`` と同一の呼び出し契約)。
    同期 / 非同期のどちらでもよい (awaitable を自動解決)。
    """

    def __init__(
        self,
        llm: Any,
        temperature: float = VOTE_TEMPERATURE,
        excerpt_window: int = EXCERPT_WINDOW_CHARS,
        excerpt_max_chars: int = EXCERPT_MAX_CHARS,
    ):
        self.llm = llm
        self.temperature = temperature
        self.excerpt_window = excerpt_window
        self.excerpt_max_chars = excerpt_max_chars

    def build_prompt(
        self,
        foreshadowing_title: str,
        foreshadowing_description: str,
        keywords: Sequence[str],
        excerpt: str,
        episode_num: int,
    ) -> str:
        """判定プロンプトを構築する。

        マスキング原則: model 名・provider 痕跡・出力元は含めない (Q8 契約)。
        """
        keyword_note = "、".join(keywords[:5]) if keywords else "なし"
        return (
            "あなたはWeb小説の編集者です。以下の本文が、指定された伏線をどこまで扱ったかを判定してください。\n"
            f"(判定対象は第{episode_num}話。伏線の参照キーワード: {keyword_note})\n"
            "\n【伏線】\n"
            f"タイトル: {foreshadowing_title}\n"
            f"内容: {foreshadowing_description or foreshadowing_title}\n"
            "\n【本文（抜粋）】\n"
            f"{excerpt}\n"
            "\n判定基準:\n"
            "- resolved: 伏線の謎・約束が本文中で明示的に解決・回収されている\n"
            "- progressed: 伏線が展開・深化されたが、回収には至っていない\n"
            "- unmentioned: 伏線にほとんど触れられていない\n"
            "\n出力は JSON のみ（コードブロック不要）。キーは以下の通り:\n"
            '  "action": "resolved" | "progressed" | "unmentioned"\n'
            '  "evidence_quote": 判断の根拠となった本文からの引用（60字以内、なければ空文字）\n'
        )

    async def vote(
        self,
        foreshadowing_id: int,
        foreshadowing_title: str,
        foreshadowing_description: str = "",
        keywords: Optional[Sequence[str]] = None,
        draft_text: str = "",
        episode_num: int = 0,
    ) -> Optional[LLMVoteResult]:
        """本文から伏線の扱いを判定する。いかなる失敗も None 投票 (P3 fail-open)。"""
        if self.llm is None or not (draft_text or "").strip():
            return None

        keyword_list = list(keywords or [])
        excerpt = build_windowed_excerpt(
            draft_text,
            [foreshadowing_title, *keyword_list],
            window=self.excerpt_window,
            max_chars=self.excerpt_max_chars,
        )
        prompt = self.build_prompt(
            foreshadowing_title=foreshadowing_title,
            foreshadowing_description=foreshadowing_description,
            keywords=keyword_list,
            excerpt=excerpt,
            episode_num=episode_num,
        )

        try:
            raw = await self._call_llm(prompt)
        except Exception as exc:  # noqa: BLE001 - P3: 投票の失敗で回収処理を止めない
            logger.debug("Foreshadowing LLM vote failed (id=%s): %s", foreshadowing_id, exc)
            return None

        parsed = _parse_vote_json(raw)
        if parsed is None:
            logger.debug("Foreshadowing LLM vote returned unparsable JSON (id=%s)", foreshadowing_id)
            return None
        action, evidence = parsed
        return LLMVoteResult(
            foreshadowing_id=foreshadowing_id,
            action=action,
            evidence_quote=evidence[:120],
            raw_response=(raw or "")[:500],
        )

    async def _call_llm(self, prompt: str) -> str:
        """duck-typed LLM 呼び出し (generate / ainvoke / predict / callable)。"""
        llm = self.llm
        if hasattr(llm, "generate"):
            res = llm.generate(prompt=prompt, temperature=self.temperature)
            if inspect.isawaitable(res):
                res = await res
        elif hasattr(llm, "ainvoke"):
            res = await llm.ainvoke(prompt)
        elif hasattr(llm, "predict"):
            res = llm.predict(prompt)
            if inspect.isawaitable(res):
                res = await res
        elif callable(llm):
            res = llm(prompt)
            if inspect.isawaitable(res):
                res = await res
        else:
            raise TypeError("llm has no usable generation interface")

        if isinstance(res, str):
            return res
        if hasattr(res, "text"):
            return str(res.text)
        if hasattr(res, "content"):
            return str(res.content)
        if isinstance(res, dict) and "content" in res:
            return str(res["content"])
        return str(res)


def _parse_vote_json(raw: str) -> Optional[tuple[VoteAction, str]]:
    """LLM 応答から action と evidence_quote を抽出する (不正なら None)。"""
    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    action = str(data.get("action", "")).strip().lower()
    if action not in _VALID_ACTIONS:
        return None
    evidence = str(data.get("evidence_quote", "") or "")
    return cast(VoteAction, action), evidence


__all__ = [
    "EXCERPT_MAX_CHARS",
    "EXCERPT_WINDOW_CHARS",
    "ForeshadowingLLMVoter",
    "LLMVoteResult",
    "VOTE_TEMPERATURE",
    "VoteAction",
    "build_windowed_excerpt",
]
