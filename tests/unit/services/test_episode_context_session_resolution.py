"""セッション解決が一意に定まることの回帰テスト。

T6 Step 3 の回帰防止。

v5.3 の M8 は「伏線側は `or repo.session`、ダイジェスト側は
`artifacts.get("session")` のみ」という**経路ごとの食い違い**だった。
正本の解決点は `src/agents/writing/episode_writer.py` のモジュールレベル
`_resolve_session(repo, session)` であり、伏線・ダイジェスト双方へ
同じ解決結果を渡している。

本テストは
  (1) ダイジェスト経路が「repo しか持たない」呼び出し元でも
      セッションを解決できること（M8 の再発防止）
  (2) 重複実装が復活していないこと
を保証する。
"""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agents.writing.episode_writer import _resolve_session

EPISODE_CONTEXT = Path("src/services/episode_context.py")
EPISODE_WRITER = Path("src/agents/writing/episode_writer.py")


class _OnlyRepo:
    """`session` を持つが `artifacts` を持たないリポジトリ（M8 の呼び出し元）。"""

    def __init__(self, session):
        self.session = session


class _FakeAsyncSession:
    """伏線/ダイジェストのリポジトリが要求する非同期セッションのスタブ。

    `_resolve_session` は「使える**非同期**セッションか」を判定する
    （`run_sync` は AsyncSession 固有）。素の文字列や `object()` を
    セッションの代用にしていると判定に掉落し、優先順位の検証ができない。
    """

    def __init__(self, label: str = ""):
        self.run_sync = lambda *a, **k: None
        self.label = label


# ── 解決そのものの意味論 ─────────────────────────────────────────


def test_explicit_session_wins():
    explicit = _FakeAsyncSession("EXPLICIT")
    assert _resolve_session(_OnlyRepo(_FakeAsyncSession("FROM_REPO")), explicit) is explicit


def test_falls_back_to_repo_session():
    """`session` 引数が None でも `repo.session` にフォールバックすること。

    M8 の本质：ダイジェスト経路は `artifacts.get("session")` しか見ず、
    repo しか持たない呼び出し元では空振りしていた。
    """
    from_repo = _FakeAsyncSession("FROM_REPO")
    assert _resolve_session(_OnlyRepo(from_repo), None) is from_repo


def test_returns_none_when_both_absent():
    assert _resolve_session(None, None) is None
    assert _resolve_session(SimpleNamespace(), None) is None


def test_rejects_non_async_session():
    """同期 Session / coroutine function は「使えるセッション」ではないので弾く。

    本番は BookRepository（**同期** Session）を渡していたため
    `await self.db.flush()` が TypeError になり、伏線回収とダイジェスト保存が
    常に警告でスキップされていた。判定が無いと握り潰されて原因不明になる。
    """
    assert _resolve_session(_OnlyRepo("SYNC_SESSION_PLACEHOLDER"), None) is None


# ── 構造の固定 ───────────────────────────────────────────────────


def _count_define(path: Path, name: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )


def test_single_definition_of_resolve_session_repo_wide():
    """リポジトリ全体で `_resolve_session` の定義が1箇所だけであること。

    2箇所 Mewari ると、経路ごとに別の解決逻辑に戻ってしまう（M8 の再発）。
    """
    offenders = []
    for path in Path("src").rglob("*.py"):
        count = _count_define(path, "_resolve_session")
        if count:
            offenders.append(f"{path.as_posix()}:{count}")
    assert offenders == [
        "src/agents/writing/episode_writer.py:1"
    ], f"_resolve_session の定義が重複している: {offenders}"


def test_episode_context_builder_has_no_dead_resolver():
    """`EpisodeContextBuilder` に未使用の `_resolve_session` が復活していないこと。

    同クラスは `ctx` を受け取らず `__init__(session)` で注入される `self.db` を
    使うため、`ctx.artifacts` 前提の実装は構造上呼び出せない。
    """
    assert _count_define(EPISODE_CONTEXT, "_resolve_session") == 0, (
        "EpisodeContextBuilder に未使用の _resolve_session が復活した"
    )


# ── 実経路の結線 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_digest_path_resolves_session_from_repo(monkeypatch):
    """repo しか持たない呼び出し元でもダイジェスト永続化まで到達すること。

    これが M8 の実害（ダイジェストだけ空振り）を直接防ぐ回帰テスト。
    """
    from src.agents.writing.episode_writer import EpisodeWriter

    reached: dict = {}

    async def _fake_digest(self, session, book_id, ep_num, written_text):
        reached["session"] = session
        reached["ep_num"] = ep_num
        return None

    monkeypatch.setattr(EpisodeWriter, "_persist_episode_digest", _fake_digest)

    session = _FakeAsyncSession("FROM_REPO")
    writer = EpisodeWriter(
        llm=None,
        context_builder=None,
        repo=_OnlyRepo(session),
        prompt_manager=None,
    )
    # repo しか session を持たない = `session=` を渡さない呼び出し形态
    await writer._post_episode_finalize(
        book_id=1,
        branch_id=1,
        ep_num=3,
        written_text="本文",
        writing_metadata=None,
        repo=None,
        session=None,
    )

    assert reached.get("session") is session, (
        "repo.session にフォールバックせず、ダイジェスト経路が空振りした（M8 の再発）"
    )
    assert reached.get("ep_num") == 3
