"""階層的逐次要約メモリの E2E テスト (PLAN_M1 Steps 19, 23).

実 SQLite (aiosqlite) + モック LLM で `EpisodeWriter.run()` を走らせ、
以下を検証する:

1. 章境界 (10話) で `digest_rollups` (level='block') が1件生成される
2. 巻境界 (50話) で `digest_rollups` (level='volume') が1件生成される
3. `ENABLE_PINNED_FACTS_EDGES=1` 時、pinned_head / pinned_tail がプロンプトに含まれる
4. rollup 生成の LLM 呼び出し回数が想定内 (+1/10話, +1/50話)
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.agents.orchestrator import AgentContext
from src.agents.writing.episode_writer import EpisodeWriter
from src.backend.database.models_digest import EpisodeDigestModel
from src.backend.database.models_foreshadowing import ForeshadowingModel
from src.backend.database.models_rollup import DigestRollupModel
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository

BOOK_ID = 1
EPISODE_NUMBER = 10


def _tables_with_fk_closure(*tables):
    """外部キーの推移閉包。SQLite でも INSERT できるようにする。"""
    collected = []
    stack = list(tables)
    while stack:
        current = stack.pop()
        if current in collected:
            continue
        collected.append(current)
        for fk in current.foreign_keys:
            stack.append(fk.column.table)
    return collected


@asynccontextmanager
async def _real_db(tmp_path):
    """digest_rollups を含む実 SQLite セッション工場。"""
    db_path = tmp_path / "hierarchical_memory.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", echo=False, connect_args={"timeout": 10}
    )
    tables = _tables_with_fk_closure(
        ForeshadowingModel.__table__,
        EpisodeDigestModel.__table__,
        DigestRollupModel.__table__,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
        for table in tables:
            if table.name == "books":
                await conn.execute(
                    insert(table).values(
                        id=BOOK_ID,
                        title="テスト作品",
                        mode="easy",
                        genre="fantasy",
                        concept="",
                        synopsis="",
                        catchcopy="",
                        style_dna="",
                        status="draft",
                        marketing_data="",
                        target_eps=60,
                    )
                )
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        yield session_factory
    finally:
        await engine.dispose()


def _raw_generation(metadata: dict) -> str:
    """モック LLM が返す「本文 + [METADATA_JSON]」"""
    return (
        "少年は剣身に手を伸ばし、祈りを捧げた。\n"
        "眩い光とともに封印が解け、聖剣の封印は静かに開いた。\n\n"
        "[METADATA_JSON]\n"
        + json.dumps(metadata, ensure_ascii=False, indent=2)
        + "\n[/METADATA_JSON]"
    )


def _make_digest_llm(ep_num: int):
    """ダイジェスト生成用のモック LLM (generate(prompt=, temperature=) で文字列返却)。"""
    m = MagicMock()
    m.generate = MagicMock(return_value=f"第{ep_num}話: 封印が解けた。")
    return m


def _make_writer(session, ep_num: int, raw: str = "PROMPT") -> EpisodeWriter:
    llm = MagicMock()
    llm.generate_text = AsyncMock(return_value=_raw_generation({}))
    # ダイジェスト生成（tier1 ラッパー経由）もモックで応答
    llm.generate = MagicMock(return_value=f"第{ep_num}話: 封印が解けた。")

    prompt_manager = MagicMock()
    prompt_manager.build_final_writing_prompt = AsyncMock(
        return_value=_raw_generation({})
    )

    repo = SimpleNamespace(session=session)
    writer = EpisodeWriter(
        llm=llm,
        context_builder=MagicMock(),
        repo=repo,
        prompt_manager=prompt_manager,
    )
    writer.logger = MagicMock()
    return writer


def _agent_ctx(ep_num: int, writing_context: dict) -> AgentContext:
    return AgentContext(
        book_id=BOOK_ID,
        branch_id=1,
        ep_num=ep_num,
        artifacts={"writing_context": writing_context, "session": None},
    )


@pytest.mark.asyncio
async def test_block_rollup_created_at_episode_10(tmp_path, monkeypatch):
    """10話目で章 rollup (block, 1-10) が1件生成される。"""
    monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "1")
    monkeypatch.setenv("ENABLE_EPISODE_DIGEST", "1")

    async with _real_db(tmp_path) as sf:
        async with sf() as session:
            writer = _make_writer(session, EPISODE_NUMBER)

            # 1〜10話の digest を事前保存 (ep10 は run() で生成される)
            from src.engine.context_compression.digest_service import (
                EpisodeDigestRepository,
                EpisodeDigestService,
            )

            repo_digest = EpisodeDigestRepository(session)
            for ep in range(1, EPISODE_NUMBER):
                await EpisodeDigestService(
                    repo=repo_digest, llm=_make_digest_llm(ep)
                ).summarize_and_save(
                    book_id=BOOK_ID, episode_num=ep, draft_text=f"第{ep}話本文"
                )

            writing_context = {
                "use_beat_to_scene": False,
                "contract_foreshadowings": [],
                "unresolved_foreshadowings": [],
            }
            await writer.run(_agent_ctx(EPISODE_NUMBER, writing_context))

            # 章 rollup (1-10) が1件存在する
            res = await session.execute(
                select(DigestRollupModel).where(
                    DigestRollupModel.level == "block",
                    DigestRollupModel.start_ep == 1,
                    DigestRollupModel.end_ep == 10,
                )
            )
            rollups = res.scalars().all()
            assert len(rollups) == 1, f"expected 1 block rollup, got {len(rollups)}"
            assert rollups[0].stale_at is None


@pytest.mark.asyncio
async def test_volume_rollup_created_at_episode_50(tmp_path, monkeypatch):
    """50話目で巻 rollup (volume, 1-50) が1件生成される。"""
    monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "1")
    monkeypatch.setenv("ENABLE_EPISODE_DIGEST", "1")

    async with _real_db(tmp_path) as sf:
        async with sf() as session:
            writer = _make_writer(session, 50)

            # 1〜49話の digest を事前保存
            from src.engine.context_compression.digest_service import (
                EpisodeDigestRepository,
                EpisodeDigestService,
            )

            repo_digest = EpisodeDigestRepository(session)
            for ep in range(1, 50):
                await EpisodeDigestService(
                    repo=repo_digest, llm=_make_digest_llm(ep)
                ).summarize_and_save(
                    book_id=BOOK_ID, episode_num=ep, draft_text=f"第{ep}話本文"
                )

            writing_context = {
                "use_beat_to_scene": False,
                "contract_foreshadowings": [],
                "unresolved_foreshadowings": [],
            }
            await writer.run(_agent_ctx(50, writing_context))

            # 巻 rollup (1-50) が1件存在する
            res = await session.execute(
                select(DigestRollupModel).where(
                    DigestRollupModel.level == "volume",
                    DigestRollupModel.start_ep == 1,
                    DigestRollupModel.end_ep == 50,
                )
            )
            rollups = res.scalars().all()
            assert len(rollups) == 1, f"expected 1 volume rollup, got {len(rollups)}"


@pytest.mark.asyncio
async def test_pinned_facts_in_prompt_when_enabled(tmp_path, monkeypatch):
    """ENABLE_PINNED_FACTS_EDGES=1 時、pinned_head / pinned_tail がプロンプトに含まれる。"""
    monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "0")
    monkeypatch.setenv("ENABLE_EPISODE_DIGEST", "1")
    monkeypatch.setenv("ENABLE_PINNED_FACTS_EDGES", "1")

    async with _real_db(tmp_path) as sf:
        async with sf() as session:
            writer = _make_writer(session, EPISODE_NUMBER)

            # 1つの契約伏線を設定
            writing_context = {
                "use_beat_to_scene": False,
                "contract_foreshadowings": [{"id": 1, "title": "竜の鱗の行方"}],
                "unresolved_foreshadowings": [
                    {"id": 2, "title": "期限切れ伏線", "planted_episode": 1,
                     "target_episode": 5, "status": "planted"}
                ],
            }
            await writer.run(_agent_ctx(EPISODE_NUMBER, writing_context))

            # build_final_writing_prompt の呼び出し引数を確認
            call_args = writer.prompt_manager.build_final_writing_prompt.call_args
            assert call_args is not None, "build_final_writing_prompt 未呼び出し"
            kwargs = call_args.kwargs
            pinned_head = kwargs.get("pinned_head", "")
            pinned_tail = kwargs.get("pinned_tail", "")

            assert "【期限超過】期限切れ伏線 の回収が未完了" in pinned_head, (
                f"pinned_head に期限超過伏線が含まれていない: {pinned_head}"
            )
            assert "【本話回収必須】竜の鱗の行方" in pinned_head, (
                f"pinned_head に契約伏線が含まれていない: {pinned_head}"
            )
            assert pinned_tail != "", "pinned_tail が空"


@pytest.mark.asyncio
async def test_flag_off_pinned_is_empty(tmp_path, monkeypatch):
    """ENABLE_PINNED_FACTS_EDGES=0 時、pinned_head / pinned_tail は空（現行出力と同一）。"""
    monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "0")
    monkeypatch.setenv("ENABLE_EPISODE_DIGEST", "1")
    monkeypatch.setenv("ENABLE_PINNED_FACTS_EDGES", "0")

    async with _real_db(tmp_path) as sf:
        async with sf() as session:
            writer = _make_writer(session, EPISODE_NUMBER)

            # 契約伏線があっても flag off なら pinned は空
            writing_context = {
                "use_beat_to_scene": False,
                "contract_foreshadowings": [{"id": 1, "title": "竜の鱗の行方"}],
                "unresolved_foreshadowings": [
                    {"id": 2, "title": "期限切れ伏線", "planted_episode": 1,
                     "target_episode": 5, "status": "planted"}
                ],
            }
            await writer.run(_agent_ctx(EPISODE_NUMBER, writing_context))

            call_args = writer.prompt_manager.build_final_writing_prompt.call_args
            assert call_args is not None, "build_final_writing_prompt 未呼び出し"
            kwargs = call_args.kwargs
            pinned_head = kwargs.get("pinned_head", "")
            pinned_tail = kwargs.get("pinned_tail", "")

            assert pinned_head == "", f"flag off で pinned_head が空でない: {pinned_head}"
            assert pinned_tail == "", f"flag off で pinned_tail が空でない: {pinned_tail}"


@pytest.mark.asyncio
async def test_rollup_llm_call_count_budget(tmp_path, monkeypatch):
    """rollup 生成の LLM 呼び出しが想定回数を超えない (+1/10話, +1/50話)。"""
    monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "1")
    monkeypatch.setenv("ENABLE_EPISODE_DIGEST", "1")

    call_count = [0]

    class CountingLLM:
        def generate(self, **kwargs):
            call_count[0] += 1
            return f"digest {call_count[0]}"

    async with _real_db(tmp_path) as sf:
        async with sf() as session:
            llm = MagicMock()
            llm.generate_text = AsyncMock(return_value=_raw_generation({}))
            llm.generate = CountingLLM().generate

            prompt_manager = MagicMock()
            prompt_manager.build_final_writing_prompt = AsyncMock(return_value="PROMPT")

            repo = SimpleNamespace(session=session)
            writer = EpisodeWriter(
                llm=llm,
                context_builder=MagicMock(),
                repo=repo,
                prompt_manager=prompt_manager,
            )
            writer.logger = MagicMock()

            # 1〜10話を順に run (ep10 で章 rollup +1)
            writing_context = {
                "use_beat_to_scene": False,
                "contract_foreshadowings": [],
                "unresolved_foreshadowings": [],
            }
            for ep in range(1, 11):
                # ep10 の直前に digest を事前保存
                if ep < 10:
                    from src.engine.context_compression.digest_service import (
                        EpisodeDigestRepository,
                        EpisodeDigestService,
                    )
                    repo_digest = EpisodeDigestRepository(session)
                    await EpisodeDigestService(
                        repo=repo_digest, llm=_make_digest_llm(ep)
                    ).summarize_and_save(
                        book_id=BOOK_ID, episode_num=ep, draft_text=f"第{ep}話本文"
                    )
                await writer.run(_agent_ctx(ep, writing_context))

            # ep10 で rollup 生成 (+1 call) → 合計 10 (digest) + 1 (rollup) = 11
            assert call_count[0] == 11, f"expected 11 LLM calls, got {call_count[0]}"
