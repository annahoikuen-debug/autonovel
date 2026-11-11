"""章完了時の自動100字事実要約生成サービス (v5.0 Step 14).

長編執筆におけるコンテキスト肥大化を防止するため、
各エピソード本文から客観的事実のみを100字〜150字以内で抽出・永続化する。
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, List, Optional
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.database.models_digest import EpisodeDigestModel
from src.engine.context_compression.rollup_config import RollupConfig

logger = logging.getLogger("digest_service")

MAX_DIGEST_LENGTH = 150
TARGET_DIGEST_LENGTH = 100


async def _call_digest_llm(llm: Any, prompt: str) -> str:
    """digest 用 LLM 呼び出し（generate / ainvoke / predict / callable 対応）。

    失敗時は空文字を返す（fail-open）。
    """
    if llm is None:
        return ""
    try:
        if hasattr(llm, "generate"):
            res = llm.generate(prompt=prompt, temperature=0.1)
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
            return ""
    except Exception as e:  # noqa: BLE001
        logger.warning(f"LLM generation failed for digest: {e}")
        return ""

    if isinstance(res, str):
        return res
    if hasattr(res, "text"):
        return res.text
    if hasattr(res, "content"):
        return str(res.content)
    if isinstance(res, dict) and "content" in res:
        return str(res["content"])
    # どの属性も持たない（例: int 42 など）場合は空文字を返し、
    # generate_episode_digest 側のフォールバック抽出に任せる（元挙動と同一）。
    return ""


async def generate_episode_digest(
    llm: Any,
    draft_text: str,
    ep_num: int,
    cod_rounds: int = 1,
) -> str:
    """エピソード本文から後続話に影響する「確定した客観的事実」のみを100文字程度で要約抽出する。

    Args:
        llm: LLMクライアント（generate, ainvoke, predict, または呼び出し可能オブジェクト）
        draft_text: 対象エピソードの本文テキスト
        ep_num: 対象エピソードの話数
        cod_rounds: Chain-of-Density 圧縮パス数。1 で現行の 1 pass と同一。
            2 以上で、1 pass 目の要約をさらに圧縮するパスを (cod_rounds-1) 回追加。

    Returns:
        150字以内の確定事実ダイジェスト文字列
    """
    if not draft_text or not draft_text.strip():
        return f"第{ep_num}話: 特筆すべき出来事なし。"

    cleaned_draft = draft_text.strip()[:2500]

    prompt = (
        f"あなたは小説の編集補助AIです。以下の第{ep_num}話本文から、"
        f"後続話のプロットや伏線・人間関係に影響する「起きた客観的事実（行動、獲得、変化など）」のみを、"
        f"感情や修飾語を省いて100文字以内で箇条書き要約してください。\n\n"
        f"【本文】\n{cleaned_draft}\n\n"
        f"【客観的事実ダイジェスト（100字以内）】"
    )

    digest_text = await _call_digest_llm(llm, prompt)

    # CoD 2 回目以降: 既存要約をさらに圧縮して密度を高める
    for _ in range(max(0, cod_rounds - 1)):
        if not digest_text or not digest_text.strip():
            break
        compress_prompt = (
            f"以下は既に要約されたテキストです。\n"
            f"冗長な表現や接続詞を省き、情報密度を高めて、"
            f"{TARGET_DIGEST_LENGTH}字以内で日本語に圧縮してください。\n\n"
            f"【要約テキスト】\n{digest_text}\n\n"
            f"【圧縮要約（{TARGET_DIGEST_LENGTH}字以内）】"
        )
        digest_text = await _call_digest_llm(llm, compress_prompt)

    # フォールバック抽出: LLMが使えないか失敗した場合は文末のキー事実を簡易抽出
    if not digest_text or not digest_text.strip():
        lines = [line.strip() for line in cleaned_draft.splitlines() if line.strip()]
        # 台詞以外の主要記述を抽出
        narrative_lines = [line for line in lines if not (line.startswith("「") or line.startswith("『"))]
        sample_lines = narrative_lines[-3:] if len(narrative_lines) >= 3 else lines[-3:]
        fallback_summary = "。".join([line.rstrip("。") for line in sample_lines])
        digest_text = f"第{ep_num}話要約: {fallback_summary}"

    # 長さ正規化 (最大 MAX_DIGEST_LENGTH 字)
    cleaned = digest_text.strip()
    if len(cleaned) > MAX_DIGEST_LENGTH:
        cleaned = cleaned[: MAX_DIGEST_LENGTH - 3].rstrip() + "..."

    return cleaned


class EpisodeDigestRepository:
    """エピソードダイジェストの非同期DB永続化リポジトリ。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_digest(
        self,
        book_id: int,
        episode_num: int,
        digest_text: str,
    ) -> EpisodeDigestModel:
        """エピソードダイジェストを新規作成または更新（Upsert）。"""
        stmt = select(EpisodeDigestModel).where(
            EpisodeDigestModel.book_id == book_id,
            EpisodeDigestModel.episode_num == episode_num,
        )
        res = await self.db.execute(stmt)
        existing = res.scalars().first()

        now = datetime.now(timezone.utc)
        if existing:
            existing.digest_text = digest_text
            existing.updated_at = now
            await self.db.flush()
            return existing
        else:
            record = EpisodeDigestModel(
                book_id=book_id,
                episode_num=episode_num,
                digest_text=digest_text,
                created_at=now,
                updated_at=now,
            )
            self.db.add(record)
            await self.db.flush()
            return record

    async def get_digests(
        self,
        book_id: int,
        limit: Optional[int] = None,
    ) -> List[EpisodeDigestModel]:
        """指定作品のダイジェストを話数昇順で取得する。"""
        stmt = (
            select(EpisodeDigestModel)
            .where(EpisodeDigestModel.book_id == book_id)
            .order_by(EpisodeDigestModel.episode_num.asc())
        )
        if limit:
            stmt = stmt.limit(limit)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_digest(
        self,
        book_id: int,
        episode_num: int,
    ) -> Optional[EpisodeDigestModel]:
        """特定話数のダイジェストを取得する。"""
        stmt = select(EpisodeDigestModel).where(
            EpisodeDigestModel.book_id == book_id,
            EpisodeDigestModel.episode_num == episode_num,
        )
        res = await self.db.execute(stmt)
        return res.scalars().first()


class EpisodeDigestService:
    """エピソードダイジェストの生成と永続化を一括管理するサービス。"""

    def __init__(
        self,
        repo: Optional[EpisodeDigestRepository] = None,
        llm: Any = None,
        cfg: Optional[RollupConfig] = None,
    ):
        self.repo = repo
        self.llm = llm
        self.cfg = cfg or RollupConfig.from_env()

    async def summarize_and_save(
        self,
        book_id: int,
        episode_num: int,
        draft_text: str,
        cod_rounds: int = 1,
    ) -> str:
        """エピソード本文から事実ダイジェストを生成し、DBに保存する。"""
        digest_text = await generate_episode_digest(
            llm=self.llm,
            draft_text=draft_text,
            ep_num=episode_num,
            cod_rounds=cod_rounds,
        )

        if self.repo is not None:
            await self.repo.save_digest(
                book_id=book_id,
                episode_num=episode_num,
                digest_text=digest_text,
            )
            # Step 14: この話を含む章・巻 rollup を stale にし、
            # 次回の digest 保存時に再生成トリガとする（retake 追従）。
            if self.cfg.rollup_enabled:
                from src.engine.context_compression.rollup_repository import (
                    DigestRollupRepository,
                )

                rollup_repo = DigestRollupRepository(self.repo.db)
                await rollup_repo.mark_stale_for_episode(
                    book_id, episode_num, self.cfg
                )

        return digest_text
