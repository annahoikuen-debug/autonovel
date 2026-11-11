"""事実保持リグレッションテスト (PLAN_M1 Step 25).

提案4 の核心を直接検証:

1. 第3話の digest に識別可能な事実を1件埋め込む
   (例: 「第3話: アルスは龍の鱗を入手した」)
2. 1〜50話を生成し、50話目の Layer2 コンテキストを構築
3. rollup off: _build_layer2_hierarchical が空を返し、legacy フォールバックに
   回ることを確認 (現行挙動の characterization)
4. rollup on: 事実が章要約経由で**保持される**ことを確認 (改善の実証)
5. 両 flag で Layer2 が LAYER2_MAX_CHARS 内に収まる

このテストが本計画の Definition of Done の核心 (T18)。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.backend.database.models_digest import EpisodeDigestModel
from src.backend.database.models_rollup import DigestRollupModel
from src.engine.context_compression.digest_service import EpisodeDigestRepository
from src.engine.context_compression.rollup_config import RollupConfig
from src.engine.context_compression.rollup_generator import RollupGenerator
from src.engine.context_compression.rollup_repository import DigestRollupRepository
from src.engine.episode_context import EpisodeContextBuilder
from src.infrastructure.database.models.base_orm import Base

BOOK_ID = 1
TARGET_EPISODE = 50
RETENTION_FACT = "アルスは龍の鱗を入手した"


@asynccontextmanager
async def _db(tmp_path):
    """episode_digests / digest_rollups / books を持つ実 SQLite セッション工場。"""
    db_path = tmp_path / "fact_retention.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", echo=False, connect_args={"timeout": 10}
    )
    async with engine.begin() as conn:
        # 全テーブルを作成（FK 閉包を自動的に解決）
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "INSERT INTO books (id, title, mode, genre, concept, synopsis, catchcopy, "
                "style_dna, status, marketing_data, target_eps, ai_assistant_config) "
                "VALUES (:id, :title, :mode, :genre, :concept, :synopsis, :catchcopy, "
                ":style_dna, :status, :marketing_data, :target_eps, :ai_assistant_config)"
            ),
            {
                "id": BOOK_ID, "title": "テスト作品", "mode": "easy", "genre": "fantasy",
                "concept": "", "synopsis": "", "catchcopy": "", "style_dna": "",
                "status": "draft", "marketing_data": "", "target_eps": 60,
                "ai_assistant_config": json.dumps({"enabled": False}),
            },
        )
    sf = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield sf
    finally:
        await engine.dispose()


class _MockLLM:
    def generate(self, **kwargs):
        return "digest text"


class TestFactRetention:
    """中盤の事実保持 (提案4 の価値) を検証する。"""

    async def _save_digests(self, session: AsyncSession, override_ep3: bool = False):
        repo = EpisodeDigestRepository(session)
        for ep in range(1, TARGET_EPISODE + 1):
            text = (
                f"第3話: {RETENTION_FACT}。" if ep == 3 and override_ep3 else f"第{ep}話本文"
            )
            await repo.save_digest(
                book_id=BOOK_ID, episode_num=ep, digest_text=text
            )

    @pytest.mark.asyncio
    async def test_rollup_off_hierarchical_returns_empty(self, tmp_path, monkeypatch):
        """rollup off: _build_layer2_hierarchical は空を返し、legacy フォールバックへ。"""
        monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "0")
        monkeypatch.setenv("ENABLE_EPISODE_DIGEST", "1")

        async with _db(tmp_path) as sf:
            async with sf() as session:
                await self._save_digests(session, override_ep3=True)

                builder = EpisodeContextBuilder(db=session)
                hierarchical = await builder._build_layer2_hierarchical(
                    book_id=BOOK_ID, current_ep=TARGET_EPISODE
                )

                # rollup off では階層テキストは空 (legacy フォールバックへ)
                assert hierarchical.get("text") == "", (
                    f"rollup off で _build_layer2_hierarchical が空でない: "
                    f"{hierarchical.get('text')[:200]}"
                )

    @pytest.mark.asyncio
    async def test_rollup_on_fact_is_retained(self, tmp_path, monkeypatch):
        """rollup on: 事実が章要約経由で**保持される**。"""
        monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "1")
        monkeypatch.setenv("ENABLE_EPISODE_DIGEST", "1")

        async with _db(tmp_path) as sf:
            async with sf() as session:
                await self._save_digests(session, override_ep3=True)

                # 章 rollup (1-10) を生成 (ep10 で境界)
                rollup_cfg = RollupConfig.from_env()
                repo_rollup = DigestRollupRepository(session)
                generator = RollupGenerator(rollup_cfg, llm=_MockLLM())

                res = await session.execute(
                    select(EpisodeDigestModel).where(
                        EpisodeDigestModel.book_id == BOOK_ID,
                        EpisodeDigestModel.episode_num.between(1, 10),
                    )
                )
                block_digests = {
                    int(r.episode_num): (r.digest_text or "")
                    for r in res.scalars().all()
                }
                block_text = await generator.generate_block_rollup(
                    BOOK_ID, (1, 10), block_digests
                )
                assert block_text, "章 rollup 生成に失敗"
                await repo_rollup.upsert_rollup(
                    BOOK_ID, "block", 1, 10, block_text
                )

                builder = EpisodeContextBuilder(db=session)
                hierarchical = await builder._build_layer2_hierarchical(
                    book_id=BOOK_ID, current_ep=TARGET_EPISODE
                )
                layer2_text = hierarchical.get("text", "")

                # 第3話の事実が章要約経由で**保持されている** (改善の実証)
                assert RETENTION_FACT in layer2_text, (
                    f"rollup on でも事実が失われている: {layer2_text[:300]}"
                )

                # Layer2 が LAYER2_MAX_CHARS 内に収まる
                max_chars = builder.LAYER2_MAX_CHARS
                assert len(layer2_text) <= max_chars, (
                    f"rollup on で Layer2 が上限超過: {len(layer2_text)} > {max_chars}"
                )
