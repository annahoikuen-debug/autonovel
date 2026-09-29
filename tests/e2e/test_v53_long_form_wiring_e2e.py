"""v5.3 長編配線 E2E テスト（Step 34）。

モック LLM + **実 SQLite（aiosqlite）** で `EpisodeWriter.run()` まで走らせ、
以下の4点が「実経路で実際に起きている」ことを証明する:

  1. 伏線の自動回収（`planted → resolved`）が `run()` 内で発火する
  2. 最終プロンプトに契約伏線（`[伏線ID: n]` と `foreshadowings` 配列）が入る
  3. 話終了後に `episode_digests` へ1行が永続化される
  4. 3層記憶（Layer1/2/3）が実プロンプトの本文まで届いている
"""

from __future__ import annotations

import json
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
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository

EPISODE_NUMBER = 12
FORESHADOWING_ID = 77
BOOK_ID = 1


def _tables_with_fk_closure(*tables) -> list:
    """外部キーの推移閉包。水tegrity制約のある SQLite でも INSERT できるようにする。"""
    collected: list = []
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
    """伏線・ダイジェスト・作品行を持つ実 SQLite セッション工場を返す。"""
    db_path = tmp_path / "v53_long_form.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", echo=False, connect_args={"timeout": 10}
    )
    tables = _tables_with_fk_closure(
        ForeshadowingModel.__table__, EpisodeDigestModel.__table__
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
                        target_eps=30,
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


def _metadata_payload() -> dict:
    return {
        "episode_number": EPISODE_NUMBER,
        "foreshadowings": [
            {
                "foreshadowing_id": FORESHADOWING_ID,
                "action": "resolved",
                "rationale": "聖剣の封印が解けた",
                "excerpt": "聖剣の封印は静かに開いた",
            }
        ],
        "word_count_estimate": 2400,
        "unresolved_notes": [],
    }


def _make_writer(session, raw: str, prompt: str = "PROMPT") -> EpisodeWriter:
    llm = MagicMock()
    llm.generate_text = AsyncMock(return_value=raw)
    # ダイジェスト生成（tier1 ラッパー経由）もモックで応答させる
    llm.generate = MagicMock(side_effect=lambda **kwargs: "第12話: 封印が解けた。")

    prompt_manager = MagicMock()
    prompt_manager.build_final_writing_prompt = AsyncMock(return_value=prompt)

    repo = SimpleNamespace(session=session)
    writer = EpisodeWriter(
        llm=llm,
        context_builder=MagicMock(),
        repo=repo,
        prompt_manager=prompt_manager,
    )
    writer.logger = MagicMock()
    return writer


def _agent_ctx(writing_context: dict) -> AgentContext:
    return AgentContext(
        book_id=BOOK_ID,
        branch_id=1,
        ep_num=EPISODE_NUMBER,
        artifacts={"writing_context": writing_context},
    )


# ── テスト1: 伏線自動回収が本番パスで発火する ────────────────────


@pytest.mark.asyncio
async def test_foreshadowing_auto_resolve_fires_in_production_path(tmp_path):
    """`EpisodeWriter.run()` により伏線1本が実際に `planted → resolved` になる。"""
    async with _real_db(tmp_path) as sf:
        async with sf() as setup_session:
            record = ForeshadowingModel(
                book_id=BOOK_ID,
                title="聖剣の封印",
                description="古代遺跡で発見された封印された剣",
                planted_episode=1,
                target_episode=EPISODE_NUMBER,
                status="planted",
                scope="long_term",
            )
            setup_session.add(record)
            await setup_session.commit()
            foreshadowing_id = record.id

        async with sf() as session:
            writer = _make_writer(session, _raw_generation(_metadata_payload()))
            ctx = _agent_ctx(
                {
                    "use_beat_to_scene": False,
                    "genre": "fantasy",
                    "prose_refiner_enabled": False,
                    # プロンプトに渡した契約伏線と同一の ID
                    "contract_foreshadowings": [
                        {"id": foreshadowing_id, "title": "聖剣の封印"}
                    ],
                }
            )
            result = await writer.run(ctx)
            await session.commit()

        assert result.error is None
        assert "聖剣の封印" in result.artifacts["written_text"]
        assert "[METADATA_JSON]" not in result.artifacts["written_text"]
        assert result.artifacts["writing_metadata"] is not None

        async with sf() as verify:
            row = (
                await verify.execute(
                    select(ForeshadowingModel).where(
                        ForeshadowingModel.id == foreshadowing_id
                    )
                )
            ).scalar_one()
            assert row.status == "resolved", (
                f"伏線が resolved になっていない（status={row.status}）"
            )
            assert row.resolved_episode == EPISODE_NUMBER


# ── テスト2: 最終プロンプトに契約伏線が入る ─────────────────────


@pytest.mark.asyncio
async def test_final_prompt_contains_contract_foreshadowing(tmp_path):
    """実 `PromptManager` で描画した最終プロンプトに契約伏線IDが含まれる。"""
    from prompts.manager import PromptManager

    pm = PromptManager()
    prompt = await pm.build_final_writing_prompt(
        ep_num=EPISODE_NUMBER,
        plot_data={"detailed_blueprint": "クライマックスのプロット"},
        script_text="台本",
        target_word_count=2400,
        book_id=None,
        contract_foreshadowings=[
            {
                "id": FORESHADOWING_ID,
                "title": "聖剣の封印",
                "description": "古代遺跡の封印された剣",
                "planted_episode": 1,
                "target_episode": EPISODE_NUMBER,
                "scope": "long_term",
            }
        ],
        unresolved_foreshadowings=[
            {
                "id": 21,
                "title": "黒騎士の紋章",
                "description": "紋章の出所",
                "planted_episode": 2,
                "target_episode": 30,
                "status": "planted",
            }
        ],
    )

    assert f"[伏線ID: {FORESHADOWING_ID}]" in prompt
    assert "聖剣の封印" in prompt
    assert "[伏線ID: 21]" in prompt
    # メタデータ出力スキーマ（foreshadowings 配列）も同時に含まれる
    assert '"foreshadowings"' in prompt
    assert "[METADATA_JSON]" in prompt
    # 契約IDがメタデータの型見本にも現れる（LLM が ID を報告できるようにする）
    metadata_block = prompt[prompt.index("{") : prompt.rindex("}") + 1]
    echoed = json.loads(metadata_block)
    assert echoed["foreshadowings"][0]["foreshadowing_id"] == FORESHADOWING_ID


# ── テスト3: 話終了後にダイジェストが永続化される ────────────────


@pytest.mark.asyncio
async def test_digest_is_persisted_after_episode(tmp_path):
    """`EpisodeWriter.run()` 後、`episode_digests` に1行が生成される。"""
    async with _real_db(tmp_path) as sf:
        async with sf() as session:
            writer = _make_writer(session, _raw_generation(_metadata_payload()))
            await writer.run(_agent_ctx({"use_beat_to_scene": False, "genre": "fantasy"}))
            await session.commit()

        async with sf() as verify:
            rows = (
                (
                    await verify.execute(
                        select(EpisodeDigestModel).where(
                            EpisodeDigestModel.book_id == BOOK_ID,
                            EpisodeDigestModel.episode_num == EPISODE_NUMBER,
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 1, f"ダイジェストが1行生成されていない: {len(rows)}"
            assert rows[0].digest_text
            assert len(rows[0].digest_text) <= 200


# ── テスト4: 3層記憶が実プロンプトに届く ────────────────────────


@pytest.mark.asyncio
async def test_three_layer_context_reaches_prompt(tmp_path):
    """`EpisodeContextBuilder` 相当の3層テキストが最終プロンプトの本文に含まれる。"""
    from prompts.manager import PromptManager

    from src.agents.prompt_composer import PromptComposer

    three_layer = {
        "layer1_bible": {"text": "【アルス】役割: 主人公"},
        "layer2_summary": {
            "text": "【過去エピソード要約】\n第1話: 封印された剣を発見\n"
            "【未回収伏線一覧】\n  - 「聖剣の封印」（第1話設置, 第12話回収目標）"
        },
        "layer3_previous": {"text": "封印の前で剣が低く鳴った。"},
    }

    async with _real_db(tmp_path) as sf:
        async with sf() as session:
            writer = _make_writer(session, _raw_generation(_metadata_payload()))

            # 実 PromptManager を差し込む（モック.render を介さず本物の描画を通す）
            real_pm = PromptManager()
            captured: dict[str, str] = {}

            async def _capturing_build(**kwargs):
                prompt = await real_pm.build_final_writing_prompt(**kwargs)
                captured["prompt"] = prompt
                return prompt

            writer.prompt_manager = SimpleNamespace(
                build_final_writing_prompt=_capturing_build
            )

            ctx = _agent_ctx(
                {
                    "use_beat_to_scene": False,
                    "genre": "fantasy",
                    "prose_refiner_enabled": False,
                    "plot": {"detailed_blueprint": "プロット"},
                    "three_layer_context": three_layer,
                }
            )
            await writer.run(ctx)

    prompt = captured["prompt"]
    assert "【Layer1: 世界観・キャラクター設定（不変）】" in prompt
    assert "【Layer2: 過去の確定事実タイムライン】" in prompt
    assert "【Layer3: 直前エピソードの原文】" in prompt
    assert "アルス" in prompt
    assert "封印された剣を発見" in prompt
    assert "封印の前で剣が低く鳴った。" in prompt


# ── 補助: 伏線リポジトリの「延期不能 → 回収放棄」経路 ────────────


@pytest.mark.asyncio
async def test_abandon_is_called_when_postponement_impossible(tmp_path):
    """作品末尾で回収できない伏線は `abandoned` へ遷移する（KPI の実数値化）。"""
    from src.services.foreshadowing_service import ForeshadowingService

    async with _real_db(tmp_path) as sf:
        async with sf() as setup_session:
            record = ForeshadowingModel(
                book_id=BOOK_ID,
                title="回収できない伏線",
                description="d",
                planted_episode=1,
                target_episode=5,
                status="planted",
                scope="short_term",
            )
            setup_session.add(record)
            await setup_session.commit()
            foreshadowing_id = record.id

        async with sf() as session:
            service = ForeshadowingService(DbForeshadowingRepository(session))
            await service.check_and_resolve(
                book_id=BOOK_ID,
                episode_num=30,
                draft_text="特に触れない本文。",
                writing_metadata=None,
                contract_ids=[foreshadowing_id],
                total_episodes=30,
            )
            await session.commit()

        async with sf() as verify:
            row = (
                await verify.execute(
                    select(ForeshadowingModel).where(
                        ForeshadowingModel.id == foreshadowing_id
                    )
                )
            ).scalar_one()
            assert row.status == "abandoned", (
                f"作品末尾の伏線が abandoned になっていない（status={row.status}）"
            )
