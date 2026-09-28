"""services/context_compression: 事実ダイジェスト生成/永続化と3層ローリング記憶。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.context_compression.digest_service import (
    MAX_DIGEST_LENGTH,
    EpisodeDigestRepository,
    EpisodeDigestService,
    generate_episode_digest,
)
from src.services.context_compression.rolling_memory import RollingMemoryBuilder


# --------------------------------------------------------------------------
# generate_episode_digest
# --------------------------------------------------------------------------
async def test_digest_empty_text():
    assert await generate_episode_digest(None, "   ", 3) == "第3話: 特筆すべき出来事なし。"


async def test_digest_generate_returns_str():
    llm = SimpleNamespace(generate=lambda prompt, temperature=None: "要約A")
    assert await generate_episode_digest(llm, "本文", 1) == "要約A"


async def test_digest_generate_awaitable_and_attributes():
    class Attr:
        text = "text版"

    class Content:
        content = ["content版"]

    async def agen(prompt, temperature=None):
        return Attr()

    assert await generate_episode_digest(SimpleNamespace(generate=agen), "b", 1) == "text版"
    assert await generate_episode_digest(SimpleNamespace(generate=lambda prompt, temperature=None: Attr()), "b", 1) == "text版"
    assert await generate_episode_digest(SimpleNamespace(generate=lambda prompt, temperature=None: Content()), "b", 1) == str(Content().content)
    assert await generate_episode_digest(SimpleNamespace(generate=lambda prompt, temperature=None: {"content": "dict版"}), "b", 1) == "dict版"
    res = await generate_episode_digest(SimpleNamespace(generate=lambda prompt, temperature=None: 42), "b", 1)
    assert res.startswith("第1話要約:")


async def test_digest_ainvoke_branch():
    class Res:
        content = "invoke版"

    llm = SimpleNamespace(ainvoke=AsyncMock(return_value=Res()))
    assert await generate_episode_digest(llm, "b", 1) == "invoke版"

    llm2 = SimpleNamespace(ainvoke=AsyncMock(return_value="plain"))
    assert await generate_episode_digest(llm2, "b", 1) == "plain"


async def test_digest_predict_branch():
    async def apredict(prompt):
        return "predict版"

    assert await generate_episode_digest(SimpleNamespace(predict=apredict), "b", 1) == "predict版"
    assert await generate_episode_digest(SimpleNamespace(predict=lambda p: "sync版"), "b", 1) == "sync版"


async def test_digest_callable_branch():
    async def acall(prompt):
        return "callable版"

    assert await generate_episode_digest(acall, "b", 1) == "callable版"
    assert await generate_episode_digest(lambda p: "sync callable", "b", 1) == "sync callable"


async def test_digest_llm_failure_falls_back():
    def boom(prompt, temperature=None):
        raise RuntimeError("llm down")

    out = await generate_episode_digest(SimpleNamespace(generate=boom), "行1\n「台詞」\n行3\n行4", 2)
    assert out.startswith("第2話要約:")
    assert "行1" in out and "行3" in out
    assert "台詞" not in out


async def test_digest_fallback_few_lines():
    out = await generate_episode_digest(None, "「台詞」", 4)
    assert out.startswith("第4話要約:")


async def test_digest_truncation():
    llm = SimpleNamespace(generate=lambda prompt, temperature=None: "あ" * 400)
    out = await generate_episode_digest(llm, "b", 1)
    assert len(out) == MAX_DIGEST_LENGTH
    assert out.endswith("...")


async def test_digest_prompt_truncates_long_draft():
    captured = {}

    def gen(prompt, temperature=None):
        captured["prompt"] = prompt
        return "ok"

    await generate_episode_digest(SimpleNamespace(generate=gen), "x" * 5000, 9)
    assert "x" * 2501 not in captured["prompt"]
    assert "第9話" in captured["prompt"]


# --------------------------------------------------------------------------
# EpisodeDigestRepository / EpisodeDigestService
# --------------------------------------------------------------------------
def _result(first=None, all_=()):
    res = MagicMock()
    scalars = MagicMock()
    scalars.first.return_value = first
    scalars.all.return_value = list(all_)
    res.scalars.return_value = scalars
    return res


async def test_repository_save_new_and_update():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(first=None))
    db.flush = AsyncMock()
    repo = EpisodeDigestRepository(db)
    rec = await repo.save_digest(1, 1, "digest")
    assert rec.digest_text == "digest"
    db.add.assert_called_once_with(rec)

    existing = SimpleNamespace(digest_text="old", updated_at=None)
    db.execute = AsyncMock(return_value=_result(first=existing))
    same = await repo.save_digest(1, 1, "new")
    assert same is existing
    assert existing.digest_text == "new"


async def test_repository_get_digests_with_and_without_limit():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(all_=[1, 2]))
    repo = EpisodeDigestRepository(db)
    assert await repo.get_digests(1) == [1, 2]
    assert await repo.get_digests(1, limit=1) == [1, 2]


async def test_repository_get_digest():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(first="d"))
    assert await EpisodeDigestRepository(db).get_digest(1, 2) == "d"


async def test_digest_service_summarize_and_save():
    repo = MagicMock()
    repo.save_digest = AsyncMock()
    llm = SimpleNamespace(generate=lambda prompt, temperature=None: "要約")
    svc = EpisodeDigestService(repo, llm)
    assert await svc.summarize_and_save(1, 1, "本文") == "要約"
    repo.save_digest.assert_awaited_once_with(
        book_id=1, episode_num=1, digest_text="要約"
    )

    svc2 = EpisodeDigestService(None, None)
    assert await svc2.summarize_and_save(1, 1, "本文")


# --------------------------------------------------------------------------
# RollingMemoryBuilder
# --------------------------------------------------------------------------
def test_normalize_digest_variants():
    b = RollingMemoryBuilder()
    assert b._normalize_digest("  s  ") == "s"
    assert b._normalize_digest({"episode_num": 3, "digest_text": "d"}) == "第3話: d"
    assert b._normalize_digest({"ep": 4, "text": "t"}) == "第4話: t"
    assert b._normalize_digest({"digest_text": "t"}) == "t"
    assert b._normalize_digest(SimpleNamespace(episode_num=2, digest_text="x")) == "第2話: x"
    assert b._normalize_digest(SimpleNamespace(digest_text="y")) == "y"
    assert b._normalize_digest(SimpleNamespace()) == "namespace()"


def test_filter_and_window_basic():
    b = RollingMemoryBuilder(max_recent_digests=5)
    assert b.filter_and_window_digests([]) == []
    assert b.filter_and_window_digests(["a", "b", None, "c"]) == ["a", "b", "c"]


def test_filter_and_window_compresses():
    b = RollingMemoryBuilder(max_recent_digests=4, preserve_initial_digests=2)
    out = b.filter_and_window_digests([f"d{i}" for i in range(1, 9)])
    assert out[0] == "d1" and out[1] == "d2"
    assert "省略" in out[2]
    assert out[-2:] == ["d7", "d8"]
    assert len(out) == 5


def test_filter_and_window_all_recent():
    b = RollingMemoryBuilder(max_recent_digests=3, preserve_initial_digests=0)
    out = b.filter_and_window_digests(["a", "b", "c", "d"])
    assert "省略" in out[0]
    assert out[-2:] == ["c", "d"]


def test_truncate_prev_episode():
    b = RollingMemoryBuilder(max_prev_episode_chars=10)
    assert b.truncate_prev_episode("") == "なし"
    assert b.truncate_prev_episode("  short  ") == "short"
    out = b.truncate_prev_episode("y" * 100)
    assert out.startswith("……（前略）")
    assert len(out) == len("……（前略）\n") + 10


def test_build_context_layers():
    b = RollingMemoryBuilder()
    ctx = b.build_context("世界設定", ["第1話: a"], "直前本文")
    assert "【設定・世界観バイブル】" in ctx
    assert "【過去話の確定事実タイムライン】" in ctx
    assert "【直前エピソード本文】" in ctx
    assert "世界設定" in ctx

    empty = b.build_context("", [], "")
    assert "（世界観設定なし）" in empty
    assert "なし" in empty


def test_build_context_budget_guard():
    b = RollingMemoryBuilder(
        max_recent_digests=10, max_total_chars=400, max_total_tokens=10_000
    )
    digests = [f"第{i}話: " + "あ" * 200 for i in range(1, 10)]
    ctx = b.build_context("設定", digests, "本文")
    assert len(ctx) < 10_000
    assert "第1話" in ctx


def test_build_context_prev_episode_shortening():
    b = RollingMemoryBuilder(
        max_recent_digests=2, max_total_chars=300, max_total_tokens=10_000
    )
    ctx = b.build_context("x" * 250, ["d1", "d2"], "あ" * 5000)
    assert len(ctx) < 5000
    assert "前略" in ctx


def test_estimate_tokens_and_stats():
    b = RollingMemoryBuilder()
    assert b.estimate_tokens("") == 0
    assert b.estimate_tokens("あ") == 2
    stats = b.get_context_stats("設定", ["d1", "d2"], "本文")
    assert stats["past_digests_count_raw"] == 2
    assert stats["past_digests_count_windowed"] == 2
    assert stats["prev_episode_chars"] == 2
    assert stats["total_chars"] > 0
    assert stats["estimated_tokens"] > 0
