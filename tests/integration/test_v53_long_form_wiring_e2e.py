"""v5.3 長編配線 結合テスト（サブエージェント B: コンテキスト配線）。

対象:
  - B-P1 `generator.py` が `contract_foreshadowings` キーを渡す
  - B-P2 `EpisodeWriter` が `build_context()`（= `ContextBuilderAgent`）で
    `writing_context` を**マージ**し、契約伏線 ID をプロンプトに届ける

 여기서 は **プロンプト文字列そのもの**を assert する
（内部メソッドの呼び出し回数ではなく、実際に LLM が見る文字列で担保する）。
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.agents.orchestrator import AgentContext, AgentResult
from src.agents.writing.episode_writer import EpisodeWriter
from src.backend.database.models_digest import EpisodeDigestModel
from src.backend.database.models_foreshadowing import ForeshadowingModel
from src.infrastructure.database.models.base_orm import Base

BOOK_ID = 1
EPISODE_NUMBER = 12


def _tables_with_fk_closure(*tables) -> list:
    """外部キーの推移閉包。FK 制約のある SQLite でも INSERT できるようにする。"""
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
    db_path = tmp_path / "v53_wiring_b.db"
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


def _fake_repo(session) -> SimpleNamespace:
    """`ContextBuilderAgent` が呼ぶ repo メソッドを全部 AsyncMock にした検証用 repo。"""
    repo = SimpleNamespace(session=session)
    repo.get_plot = AsyncMock(return_value=None)
    repo.get_book = AsyncMock(return_value=None)
    repo.get_latest_bible = AsyncMock(return_value=None)
    repo.get_all_characters = AsyncMock(return_value=[])
    repo.get_chapter = AsyncMock(return_value=None)
    return repo


class _CapturingPromptManager:
    """実 `PromptManager` を呼びつつ、最終プロンプト文字列を保存する。"""

    def __init__(self) -> None:
        from prompts.manager import PromptManager

        self._inner = PromptManager()
        self.prompts: list[str] = []

    async def build_final_writing_prompt(self, **kwargs):
        prompt = await self._inner.build_final_writing_prompt(**kwargs)
        self.prompts.append(prompt)
        return prompt


def _make_writer(session, repo=None) -> EpisodeWriter:
    from src.agents.context_builder_agent import ContextBuilderAgent

    llm = MagicMock()
    llm.generate_text = AsyncMock(return_value="少年は剣身に手を伸ばし、祈りを捧げた。")
    llm.generate = MagicMock(side_effect=lambda **kwargs: "要約")

    return EpisodeWriter(
        llm=llm,
        context_builder=ContextBuilderAgent(repo=repo, llm=llm),
        repo=repo if repo is not None else SimpleNamespace(session=session),
        prompt_manager=_CapturingPromptManager(),
    )


def _agent_ctx(session, writing_context: dict) -> AgentContext:
    return AgentContext(
        book_id=BOOK_ID,
        branch_id=1,
        ep_num=EPISODE_NUMBER,
        artifacts={
            "writing_context": writing_context,
            "repo": SimpleNamespace(session=session),
            "session": session,
        },
    )


# ── B-P1: generator がキーを渡す ────────────────────────────────


def _generator_context_keys() -> set[str]:
    """`generator.py` が組み立てる context のキーを静的に取り出す。"""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "agents" / "writing" / "generator.py"
    tree = ast.parse(src.read_text("utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        literals = [k.value for k in node.keys if isinstance(k, ast.Constant)]
        # 「use_beat_to_scene」を含む dict が `_write_single_episode_core` の
        # 簡易版 context である（ 다른関数にはこのキーの dict が無い）。
        if "use_beat_to_scene" not in literals:
            continue
        keys.update(v for v in literals if isinstance(v, str))
    return keys


class TestGeneratorContextKeys:
    def test_generator_context_has_contract_foreshadowings_key(self):
        """B-P1: `generator.py` の context に `contract_foreshadowings` キーが存在する。

        キーの存在だけが契約（値は `EpisodeWriter` が埋める）。
        """
        assert "contract_foreshadowings" in _generator_context_keys()

    async def test_generator_run_reaches_writer_with_contract_key(self):
        """B-P1 結合: `WritingGenerator` 4話以降の経路がキーを内涵した context を `run()` へ渡す。"""
        from src.agents.writing import generator as generator_mod

        captured: dict = {}

        class _StubWriter:
            def __init__(self, **kwargs):
                pass

            async def run(self, ctx: AgentContext) -> AgentResult:
                captured["writing_context"] = dict(ctx.artifacts.get("writing_context") or {})
                return AgentResult(
                    next_agent=None,
                    artifacts={"written_text": "テスト本文"},
                    error=None,
                )

        original = generator_mod.EpisodeWriter
        generator_mod.EpisodeWriter = _StubWriter
        try:
            gen = generator_mod.WritingGenerator(
                repo=SimpleNamespace(save_chapter=AsyncMock(return_value=None)),
                llm=MagicMock(),
            )
            await gen._write_single_episode_core(book_id=BOOK_ID, ep_num=4)
        finally:
            generator_mod.EpisodeWriter = original

        assert captured, "generator が EpisodeWriter.run() を呼んでいない"
        assert "contract_foreshadowings" in captured["writing_context"]

    async def test_generator_run_keeps_target_word_count(self):
        """B-P1/B-T4: generator が渡す `target_word_count` 等が context に残る。"""
        from src.agents.writing import generator as generator_mod

        captured: dict = {}

        class _StubWriter:
            def __init__(self, **kwargs):
                pass

            async def run(self, ctx: AgentContext) -> AgentResult:
                captured["writing_context"] = dict(ctx.artifacts.get("writing_context") or {})
                return AgentResult(
                    next_agent=None, artifacts={"written_text": "テスト本文"}, error=None
                )

        original = generator_mod.EpisodeWriter
        generator_mod.EpisodeWriter = _StubWriter
        try:
            gen = generator_mod.WritingGenerator(
                repo=SimpleNamespace(save_chapter=AsyncMock(return_value=None)),
                llm=MagicMock(),
            )
            await gen._write_single_episode_core(
                book_id=BOOK_ID, ep_num=5, target_word_count=3333, passion=1.75
            )
        finally:
            generator_mod.EpisodeWriter = original

        assert captured["writing_context"]["target_word_count"] == 3333
        assert captured["writing_context"]["passion"] == 1.75


# ── B-T1 / B-T2: プロンプト文字列にアンカーが出る / 出ない ─────


@pytest.mark.asyncio
async def test_b_t1_contract_anchor_appears_in_prompt(tmp_path):
    """B-T1: `contract_foreshadowings` に ID があるとき、**プロンプト文字列**に
    `[伏線ID: n]` が実際に出る（内部呼び出し回数ではなく文字列で assert）。"""
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
            repo = _fake_repo(session)
            writer = _make_writer(session, repo=repo)
            ctx = _agent_ctx(
                session,
                {
                    # 旧一括生成経路（`use_beat_to_scene=False`）を使う。
                    # `write()` → `PromptComposer` → 実 `PromptManager` を通す。
                    "use_beat_to_scene": False,
                    "genre": "fantasy",
                    "prose_refiner_enabled": False,
                    # B-P1 が作る「空の器」。EpisodeWriter が埋める。
                    "contract_foreshadowings": [],
                },
            )
            await writer.run(ctx)

        prompt = writer.prompt_manager.prompts[-1]
        assert f"[伏線ID: {foreshadowing_id}]" in prompt, (
            "契約伏線 ID が最終プロンプトに描画されていない。"
            "LLM は [METADATA_JSON] で回収を報告できない。"
        )
        assert "聖剣の封印" in prompt
        # メタデータの型見本にも ID が現れること（回収報告の手段）
        metadata_block = prompt[prompt.index("{") : prompt.rindex("}") + 1]
        echoed = json.loads(metadata_block)
        assert echoed["foreshadowings"][0]["foreshadowing_id"] == foreshadowing_id


@pytest.mark.asyncio
async def test_b_t2_empty_contract_renders_no_anchor(tmp_path):
    """B-T2: 契約伏線が空のとき、プロンプトに `[伏線ID:` が**出ない**。

    出ると LLM が空 ID を `[METADATA_JSON]` に書いてしまい、
    `check_and_resolve` のアンサンブル判定が壊れる。
    """
    async with _real_db(tmp_path) as sf:
        async with sf() as session:
            # 未回収伏線自体が無い状態（= 契約も背景も空）
            rows = (
                (await session.execute(select(ForeshadowingModel))).scalars().all()
            )
            assert rows == []

            repo = _fake_repo(session)
            writer = _make_writer(session, repo=repo)
            ctx = _agent_ctx(
                session,
                {
                    "use_beat_to_scene": False,
                    "genre": "fantasy",
                    "prose_refiner_enabled": False,
                    "contract_foreshadowings": [],
                },
            )
            await writer.run(ctx)

    prompt = writer.prompt_manager.prompts[-1]
    assert "[伏線ID:" not in prompt, (
        "契約伏線が空なのに [伏線ID: ...] が描画されている。"
        "LLM が空 ID を回収として報告する。"
    )
    assert "【本話の絶対回収ミッション（契約伏線）】" not in prompt


# ── B-T4: マージで既存情報が失われない ─────────────────────────


@pytest.mark.asyncio
async def test_b_t4_merge_preserves_caller_context(tmp_path):
    """B-T4: `context_builder` の出力で **丸ごと置換しない**ため、
    `generator.py` が渡す `target_word_count` / `style_intensity` / `passion` が残る。"""
    async with _real_db(tmp_path) as sf:
        async with sf() as session:
            writer = _make_writer(session, repo=_fake_repo(session))
            ctx = _agent_ctx(
                session,
                {
                    "use_beat_to_scene": False,
                    "genre": "fantasy",
                    "prose_refiner_enabled": False,
                    "target_word_count": 3333,
                    "style_intensity": "high",
                    "passion": 1.75,
                    "is_easy_mode": True,
                    "regeneration_directive": "前_sceneの溜まりを直しなさい",
                    "contract_foreshadowings": [],
                },
            )
            merged = await writer._merge_full_context(
                ctx, ctx.artifacts["writing_context"]
            )

    assert merged["target_word_count"] == 3333, (
        "context_builder のデフォルト (3000 等) が target_word_count を上書きした"
    )
    assert merged["style_intensity"] == "high"
    assert merged["passion"] == 1.75
    assert merged["is_easy_mode"] is True
    assert merged["regeneration_directive"] == "前_sceneの溜まりを直しなさい"
    # ビルド側が持っていた情報（3層記憶など）も統合されている
    assert "three_layer_context" in merged


@pytest.mark.asyncio
async def test_b_t4_merge_keeps_contract_ids_from_context_builder(tmp_path):
    """B-T4 補足: 呼び出し元の空 `contract_foreshadowings` は
    `context_builder` の値で埋まる（埋まらないと配線が無意味になる）。"""
    async with _real_db(tmp_path) as sf:
        async with sf() as setup_session:
            record = ForeshadowingModel(
                book_id=BOOK_ID,
                title="黒騎士の紋章",
                description="壁に掛けられた紋章",
                planted_episode=2,
                target_episode=EPISODE_NUMBER,
                status="planted",
                scope="short_term",
            )
            setup_session.add(record)
            await setup_session.commit()

        async with sf() as session:
            writer = _make_writer(session, repo=_fake_repo(session))
            ctx = _agent_ctx(
                session,
                {
                    "use_beat_to_scene": False,
                    "target_word_count": 2000,
                    "contract_foreshadowings": [],
                },
            )
            merged = await writer._merge_full_context(
                ctx, ctx.artifacts["writing_context"]
            )

    assert [f["id"] for f in merged["contract_foreshadowings"]], (
        "context_builder が返した契約伏線が空の器で潰された"
    )
    assert merged["target_word_count"] == 2000


@pytest.mark.asyncio
async def test_b_t4_merge_survives_context_builder_failure():
    """B-T4 補足: `context_builder` が例外を投げても既存 context で執筆は続く。"""

    async def _boom(self):
        raise RuntimeError("context_builder is down")

    llm = MagicMock()
    llm.generate_text = AsyncMock(return_value="テスト本文")
    llm.generate = MagicMock(side_effect=lambda **kwargs: "要約")
    broken = MagicMock()
    broken.execute = _boom

    writer = EpisodeWriter(
        llm=llm,
        context_builder=broken,
        repo=SimpleNamespace(session=None),
        prompt_manager=MagicMock(build_final_writing_prompt=AsyncMock(return_value="P")),
    )
    ctx = AgentContext(
        book_id=BOOK_ID,
        branch_id=1,
        ep_num=EPISODE_NUMBER,
        artifacts={"writing_context": {"target_word_count": 1234}},
    )
    merged = await writer._merge_full_context(ctx, ctx.artifacts["writing_context"])
    assert merged["target_word_count"] == 1234
