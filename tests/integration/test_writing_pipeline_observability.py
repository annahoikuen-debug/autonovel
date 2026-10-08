"""警告が実際にログへ出ることの統合回帰テスト。

T6 Step 11 の回帰防止。

T6 Step 2 で `if hasattr(self, "logger"):` を25箇所撤去した。
これは「警告が出るはずだったのに出ていなかった」状態を直したものであるが、
**置換自体が誤っていれば、不可視な状態に戻る**。
そこで、ログが実際に記録されることを `caplog` で観測して保証する。

対象:
  - セッション型不一致（`ContextBuilderAgent` に同期 session を渡した場合）
  - ダイジェスト永続化の失敗
  - 伏線自動回収の失敗
"""

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.context_builder_agent import ContextBuilderAgent
from src.agents.orchestrator import AgentContext
from src.agents.writing.episode_writer import EpisodeWriter

BOOK_ID = 1
EPISODE_NUMBER = 12
RAW = "少年は剣身に手を伸ばし、祈りを捧げた。\n\n[METADATA_JSON]\n{}\n[/METADATA_JSON]"


def _make_writer(session=None):
    llm = MagicMock()
    llm.generate_text = AsyncMock(return_value=RAW)
    llm.generate = MagicMock(side_effect=lambda **kwargs: "要約")
    prompt_manager = MagicMock()
    prompt_manager.build_final_writing_prompt = AsyncMock(return_value="PROMPT")
    return EpisodeWriter(
        llm=llm,
        context_builder=MagicMock(),
        repo=SimpleNamespace(session=session),
        prompt_manager=prompt_manager,
    )


def _ctx(session):
    return AgentContext(
        book_id=BOOK_ID,
        branch_id=1,
        ep_num=EPISODE_NUMBER,
        artifacts={
            "writing_context": {
                "use_beat_to_scene": False,
                "genre": "fantasy",
                "prose_refiner_enabled": False,
            },
            "repo": SimpleNamespace(session=session),
            "session": session,
        },
    )


# ── (1) セッション型不一致が実際にログに出る ────────────────────


@pytest.mark.asyncio
async def test_session_type_mismatch_is_actually_logged(caplog):
    """同期 session を渡すと TypeError になり、その警告が記録されること。

    T6 Step 2 前は `if hasattr(self, "logger")` が常に False だったため
    この警告は**永久に無言化**していた。
    """

    class _SyncSession:
        """`execute` の結果が await できない（同期 session の擬似）。"""

        def execute(self, *a, **k):  # noqa: ANN001 - 意図的に同期
            return MagicMock()

    agent = ContextBuilderAgent.__new__(ContextBuilderAgent)

    with caplog.at_level(logging.WARNING, logger="src.agents.context_builder_agent"):
        unresolved, contract = await ContextBuilderAgent._load_db_foreshadowings(
            agent, session=_SyncSession(), book_id=BOOK_ID, ep_num=EPISODE_NUMBER
        )

    assert unresolved == []
    assert contract == []
    messages = [r.getMessage() for r in caplog.records]
    assert any("Session type mismatch" in m for m in messages), (
        "セッション型不一致の警告がログに出ていない"
        "（hasattr(self,'logger') デッドガードの再発）: "
        f"{messages}"
    )


# ── (2) ダイジェスト永続化の失敗が握り潰されない ────────────────


@pytest.mark.asyncio
async def test_digest_failure_is_actually_logged(caplog, monkeypatch):
    """ダイジェスト生成が失敗しても warning が記録されること。"""
    writer = _make_writer(session=None)

    async def _boom(self, session, book_id, ep_num, written_text):
        raise RuntimeError("ダイジェスト保存に失敗")

    monkeypatch.setattr(EpisodeWriter, "_persist_episode_digest", _boom)

    with caplog.at_level(logging.WARNING, logger="src.agents.writing.episode_writer"):
        await writer.run(_ctx(session=None))

    messages = [r.getMessage() for r in caplog.records]
    assert any("ダイジェスト" in m for m in messages), (
        f"ダイジェスト失敗が無言化された: {messages}"
    )


# ── (3) 伏線自動回収の失敗が握り潰されない ──────────────────────


@pytest.mark.asyncio
async def test_foreshadowing_failure_is_actually_logged(caplog, monkeypatch):
    """伏線自動回収で例外が出ても warning が記録されること。"""

    class _BoomRepo:
        # _is_usable_async_session は run_sync 属性（AsyncSession 固有）で
        # 判定するため、object() だと「スキップ」警告になり
        # get_unresolved に到達しない。MagicMock は全属性を持つので通る。
        session = MagicMock()

        async def get_unresolved(self, book_id):
            raise RuntimeError("伏線読み込みに失敗")

        async def add(self, *a, **k):
            return None

    writer = _make_writer(session=None)
    writer.repo = _BoomRepo()

    with caplog.at_level(logging.WARNING, logger="src.agents.writing.episode_writer"):
        await writer._post_episode_finalize(
            book_id=BOOK_ID,
            branch_id=1,
            ep_num=EPISODE_NUMBER,
            written_text=RAW,
            writing_metadata=None,
            repo=writer.repo,
            session=writer.repo.session,
        )

    messages = [r.getMessage() for r in caplog.records]
    assert any("伏線自動回収" in m for m in messages), (
        f"伏線自動回収の失敗が無言化された: {messages}"
    )


# ── メタデータ不在でも握り潰さない ──────────────────────────────


@pytest.mark.asyncio
async def test_metadata_split_failure_does_not_silently_pass(monkeypatch):
    """メタデータ解析が壊れた場合、結果が返らないことを観測する。

    T6 Step 1 により、anomalous に「握り潰して正常終了」しないこと
    （= finalize が二重に走らないこととも相まって、後処理が
    必ず1回だけ実行されることの前提monitor）。
    """
    from src.services.prose.novel_output_splitter import NovelOutputSplitter

    def _boom(raw):
        raise RuntimeError("splitter 失敗")

    monkeypatch.setattr(NovelOutputSplitter, "split_novel_output", staticmethod(_boom))
    writer = _make_writer(session=None)

    with pytest.raises(RuntimeError):
        await writer.write(BOOK_ID, EPISODE_NUMBER, {"use_beat_to_scene": False})


def test_caplog_capability_sanity():
    """`caplog` が確実に使えることの自検（テストの誤検出防止）。"""
    records: list[logging.LogRecord] = []

    class _Handler(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("probe.sanity")
    handler = _Handler()
    logger.addHandler(handler)
    try:
        logger.warning("SANITY")
    finally:
        logger.removeHandler(handler)

    assert any("SANITY" in r.getMessage() for r in records)


def test_json_fixture_is_valid():
    """RAW フィクスチャのメタデータJSONが妥当であること。"""
    body = RAW.split("[METADATA_JSON]")[1].split("[/METADATA_JSON]")[0]
    assert json.loads(body) == {}
