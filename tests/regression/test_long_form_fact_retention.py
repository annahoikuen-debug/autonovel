"""事実保持リグレッションテスト (PLAN_M1 Step 25).

提案4 の核心を直接検証:

1. 第3話の digest に識別可能な事実を1件埋め込む
   (例: 「第3話: アルスは龍の鱗を入手した」)
2. 1〜50話を生成し、50話目の Layer2 コンテキストを構築
3. rollup off: 現行仕様どおり中間省略マーカーで事実が**消える**ことを確認
   (現行挙動の characterization = 提案4 の問題の実証)
4. rollup on: 事実が**章要約経由で保持される**ことを確認 (改善の実証)
5. 両 flag で Layer2 が LAYER2_MAX_CHARS 内に収まる

このテストが本計画の Definition of Done の核心 (T18)。
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.backend.database.models_digest import EpisodeDigestModel
from src.backend.database.models_rollup import DigestRollupModel
from src.engine.context_compression.digest_service import (
    EpisodeDigestRepository,
    EpisodeDigestService,
)
from src.engine.context_compression.rollup_config import RollupConfig
from src.engine.context_compression.rollup_generator import RollupGenerator
from src.engine.context_compression.rollup_repository import DigestRollupRepository
from src.engine.episode_context import EpisodeContextBuilder
from src.infrastructure.database.models.base_orm import Base

BOOK_ID = 1
TARGET_EPISODE = 50
RETENTION_FACT = "アルスは龍の鱗を入手した"


def _tables():
    return [
        EpisodeDigestModel.__table__,
        DigestRollupModel.__table__,
    ]


@asynccontextmanager
async def _digest_db(tmp_path):
    """episode_digests のみを持つ実 SQLite セッション工場。"""
    db_path = tmp_path / "fact_retention.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", echo=False, connect_args={"timeout": 10}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_tables())
        await conn.execute(
            insert(EpisodeDigestModel.__table__).values(
                book_id=BOOK_ID,
                episode_num=0,
                digest_text="シード",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
    sf = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield sf
    finally:
        await engine.dispose()


class TestFactRetention:
    """中盤の事実保持 (提案4 の価値) を検証する。"""

    @pytest.fixture
    def mock_llm(self):
        """digest 生成用モック LLM。"""

        class M:
            def generate(self, **kwargs):
                return "digest text"

        return M()

    async def _save_digests(self, session, override_ep3: bool = False):
        """1〜50話の digest を保存。第3話は retention fact を含む。"""
        for ep in range(1, TARGET_EPISODE + 1):
            text = (
                f"第3話: {RETENTION_FACT}。" if ep == 3 and override_ep3 else f"第{ep}話本文"
            )
            await EpisodeDigestService(
                repo=EpisodeDigestRepository(session),
                llm=self.mock_llm,
            ).summarize_and_save(
                book_id=BOOK_ID, episode_num=ep, draft_text=text
            )

    def _builder(self, session) -> EpisodeContextBuilder:
        return EpisodeContextBuilder(db=session)

    @pytest.mark.asyncio
    async def test_rollup_off_fact_is_lost(self, tmp_path, monkeypatch):
        """rollup off: 中間省略マーカーで第3話の事実が**消える**。"""
        monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "0")
        monkeypatch.setenv("ENABLE_EPISODE_DIGEST", "1")

        async with _digest_db(tmp_path) as sf:
            async with sf() as session:
                await self._save_digests(session, override_ep3=True)

                builder = self._builder(session)
                context = await builder.build_context(
                    book_id=BOOK_ID, ep_num=TARGET_EPISODE
                )
                layer2_text = context.get("layer2_summary", {}).get("text", "")

                # 中間省略マーカーが現れる (現行挙動の characterization)
                assert "……" in layer2_text or "省略" in layer2_text, (
                    f"rollup off で中間省略マーカーが現れない: {layer2_text[:200]}"
                )
                # 第3話の事実が Layer2 から**消えている** (提案4 の問題の実証)
                assert RETENTION_FACT not in layer2_text, (
                    f"rollup off でも事実が残っている: {layer2_text[:300]}"
                )

                # Layer2 が LAYER2_MAX_CHARS 内に収まる
                from src.engine.episode_context import LAYER2_MAX_CHARS

                assert len(layer2_text) <= LAYER2_MAX_CHARS, (
                    f"rollup off で Layer2 が上限超過: {len(layer2_text)} > {LAYER2_MAX_CHARS}"
                )

    @pytest.mark.asyncio
    async def test_rollup_on_fact_is_retained(self, tmp_path, monkeypatch):
        """rollup on: 事実が章要約経由で**保持される**。"""
        monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "1")
        monkeypatch.setenv("ENABLE_EPISODE_DIGEST", "1")

        async with _digest_db(tmp_path) as sf:
            async with sf() as session:
                await self._save_digests(session, override_ep3=True)

                # 章 rollup (1-10) を生成 (ep10 で境界)
                rollup_cfg = RollupConfig.from_env()
                repo_rollup = DigestRollupRepository(session)
                generator = RollupGenerator(rollup_cfg, llm=self.mock_llm)

                block_digests = {
                    r.episode_num: (r.digest_text or "")
                    for r in (
                        await session.execute(
                            select(EpisodeDigestModel).where(
                                EpisodeDigestModel.book_id == BOOK_ID,
                                EpisodeDigestModel.episode_num.between(1, 10),
                            )
                        )
                    ).scalars().all()
                }
                block_text = await generator.generate_block_rollup(
                    BOOK_ID, (1, 10), block_digests
                )
                assert block_text, "章 rollup 生成に失敗"
                await repo_rollup.upsert_rollup(
                    BOOK_ID, "block", 1, 10, block_text
                )

                builder = self._builder(session)
                context = await builder.build_context(
                    book_id=BOOK_ID, ep_num=TARGET_EPISODE
                )
                layer2_text = context.get("layer2_summary", {}).get("text", "")

                # 第3話の事実が章要約経由で**保持されている** (改善の実証)
                assert RETENTION_FACT in layer2_text, (
                    f"rollup on でも事実が失われている: {layer2_text[:300]}"
                )

                # Layer2 が LAYER2_MAX_CHARS 内に収まる
                from src.engine.episode_context import LAYER2_MAX_CHARS

                assert len(layer2_text) <= LAYER2_MAX_CHARS, (
                    f"rollup on で Layer2 が上限超過: {len(layer2_text)} > {LAYER2_MAX_CHARS}"
                )
