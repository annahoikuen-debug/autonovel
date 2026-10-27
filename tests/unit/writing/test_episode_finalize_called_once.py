"""1話につき ``_post_episode_finalize`` が必ず1回だけ呼ばれることの回帰テスト。

T6 Step 1 の回帰防止。

`EpisodeWriter.run()` は `write()` を呼び、`write()` は `use_beat_to_scene=True`
（既定）のとき `write_beat_to_scene()` に委譲するHistorically、`run()` と
`write_beat_to_scene()` の双方が `_post_episode_finalize()` を呼んでいたため、
ダイジェスト生成（＝1話1回のブロッキングLLM呼出）が**話ごとに2回**発生していた。

本テストは「どちらの執筆経路でも finalize がちょうど1回」を保証する。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.orchestrator import AgentContext
from src.agents.writing.episode_writer import EpisodeWriter

EPISODE_NUMBER = 12
RAW_GENERATION = "少年は剣身に手を伸ばし、祈りを捧げた。"


def _make_writer() -> EpisodeWriter:
    """最小構成の `EpisodeWriter` を作る（LLM と prompt_manager はモック）。"""
    llm = MagicMock()
    llm.generate_text = AsyncMock(return_value=RAW_GENERATION)
    llm.generate = MagicMock(side_effect=lambda **kwargs: "要約")

    prompt_manager = MagicMock()
    prompt_manager.build_final_writing_prompt = AsyncMock(return_value="PROMPT")

    return EpisodeWriter(
        llm=llm,
        context_builder=MagicMock(),
        repo=SimpleNamespace(session=None),
        prompt_manager=prompt_manager,
    )


def _make_ctx(*, use_beat_to_scene: bool) -> AgentContext:
    """執筆経路を切り替えた `AgentContext` を作る。"""
    return AgentContext(
        book_id=1,
        branch_id=1,
        ep_num=EPISODE_NUMBER,
        artifacts={
            "writing_context": {
                "use_beat_to_scene": use_beat_to_scene,
                "genre": "fantasy",
                "prose_refiner_enabled": False,
            },
            "repo": SimpleNamespace(session=None),
            "session": None,
        },
    )


def _recorder(calls: list):
    """`_post_episode_finalize` の呼び出しを記録する代用品を作る。"""

    async def _fake(**kwargs):
        calls.append(kwargs)

    return _fake


@pytest.mark.asyncio
async def test_finalize_called_exactly_once_on_beat_to_scene_path(monkeypatch):
    """`use_beat_to_scene=True` の既定経路で finalize が二重実行されないこと。

    ダイジェスト生成は1話1回のブロッキングLLM呼出（約2500字入力）を伴うため、
    2回呼ぶと1話あたりのコストが2倍になる。
    """
    writer = _make_writer()
    # beat-to-scene 経路が実際に通るように、シーンオーケストレータだけ差し替える
    scenes = [
        SimpleNamespace(role=role, content=f"{role.value}の本文")
        for role in (
            MagicMock(value="INTRODUCTION"),
            MagicMock(value="CONFLICT"),
            MagicMock(value="HOOK"),
        )
    ]
    orchestrator = MagicMock()
    orchestrator.write_episode_scenes = AsyncMock(return_value=scenes)
    orchestrator.compose_episode = MagicMock(return_value=RAW_GENERATION)
    writer._get_scene_orchestrator = MagicMock(return_value=orchestrator)

    calls: list = []
    monkeypatch.setattr(writer, "_post_episode_finalize", _recorder(calls))

    await writer.run(_make_ctx(use_beat_to_scene=True))

    assert len(calls) == 1, (
        f"_post_episode_finalize が {len(calls)} 回呼ばれた（1回であるべき）。"
        "ダイジェスト生成のコストが2倍になっている。"
    )


@pytest.mark.asyncio
async def test_finalize_called_exactly_once_on_legacy_path(monkeypatch):
    """`use_beat_to_scene=False` の旧一括生成経路でも finalize がちょうど1回であること。"""
    writer = _make_writer()
    # 旧経路は `_get_scene_orchestrator` を叩かないことを保証する
    writer._get_scene_orchestrator = MagicMock(
        side_effect=AssertionError("旧経路でシーンオーケストレータを呼んでいる")
    )

    calls: list = []
    monkeypatch.setattr(writer, "_post_episode_finalize", _recorder(calls))

    await writer.run(_make_ctx(use_beat_to_scene=False))

    assert len(calls) == 1, (
        f"_post_episode_finalize が {len(calls)} 回呼ばれた（1回であるべき）"
    )


@pytest.mark.asyncio
async def test_finalize_receives_split_path_text(monkeypatch):
    """beat-to-scene 経路でも `run()` 側へ統合後のテキストが届くこと。

    finalize を `write_beat_to_scene()` から `run()` に寄せたことで、
    分割執筆の経路で**後処理が消えていない**ことの保証になる。
    """
    writer = _make_writer()
    scenes = [SimpleNamespace(role=MagicMock(value="HOOK"), content=RAW_GENERATION)]
    orchestrator = MagicMock()
    orchestrator.write_episode_scenes = AsyncMock(return_value=scenes)
    orchestrator.compose_episode = MagicMock(return_value=RAW_GENERATION)
    writer._get_scene_orchestrator = MagicMock(return_value=orchestrator)

    seen: dict = {}
    monkeypatch.setattr(
        writer,
        "_post_episode_finalize",
        lambda **kw: seen.update(kw) or _noop(),
    )

    await writer.run(_make_ctx(use_beat_to_scene=True))

    assert seen, "beat-to-scene 経路で finalize が呼ばれなかった"
    assert seen["written_text"] == RAW_GENERATION
    assert seen["ep_num"] == EPISODE_NUMBER
    assert seen["book_id"] == 1


@pytest.mark.asyncio
async def test_write_alone_does_not_finalize(monkeypatch):
    """`write()` を直接呼んでも finalize は走らないこと（単一実行点の保証）。

    `write()` は本文生成のみ。不管（finalize）は `run()` の責務である。
    """
    writer = _make_writer()
    writer._get_scene_orchestrator = MagicMock(
        side_effect=AssertionError("旧経路でシーンオーケストレータを呼んでいる")
    )

    calls: list = []
    monkeypatch.setattr(writer, "_post_episode_finalize", _recorder(calls))

    await writer.write(
        1,
        EPISODE_NUMBER,
        {"use_beat_to_scene": False, "prose_refiner_enabled": False},
    )

    assert calls == [], (
        f"write() から finalize が {len(calls)} 回呼ばれた。"
        "単一実行点は run() のみであるべき。"
    )


async def _noop():
    return []
