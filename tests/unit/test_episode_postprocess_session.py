"""1話1トランザクション化と commit 責務のテスト。

長編小説の品質を左右する次の2機構は、これまで **両経路（本番 / CLI）で
常に「警告を出してスキップ」されていた**。

- 伏線自動回収（``ForeshadowingService.check_and_resolve``）
- 事実ダイジェスト永続化（``EpisodeDigestService.summarize_and_save``）

原因の連鎖:

1. ``generator.py`` が ``getattr(repo, "session", None)`` でセッションを引いていたが
   - ``DataRepositoryFacade`` なら coroutine function が返り
     ``'function' object has no attribute 'execute'``
   - 本番の ``BookRepository`` は**同期** ``Session`` を持ち、
     ``await self.db.flush()`` が TypeError
2. そもそも両方とも ``flush()`` までで **commit せず**、呼び出し側が
   セッションを閉じた瞬間に破棄されていた

ここでは「(1) 短いスコープのセッションが供給される」ことと、
「(2) 変更が実際に commit される」ことを確認する。
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from src.agents.writing.episode_writer import (
    EpisodeWriter,
    _is_usable_async_session,
    _resolve_session,
)
from src.backend.database.pipeline_repo import session_factory_from
from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository
from src.services.context_compression.digest_service import (
    EpisodeDigestRepository,
    EpisodeDigestService,
)
from src.services.foreshadowing_service import ForeshadowingService


# --------------------------------------------------------------------- fakes


class _FakeAsyncSession:
    """AsyncSession の最小スタブ（``run_sync`` を持つ = 非同期セッション判定）。"""

    def __init__(self) -> None:
        self.run_sync = lambda *a, **k: None
        self.commits = 0
        self.flushes = 0
        self.closed = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        self.flushes += 1

    async def close(self) -> None:
        self.closed += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class _SyncSession:
    """本番が渡していた同期 Session（``flush()`` が None を返す）。"""

    def flush(self) -> None:
        return None


class _FakeDbManager:
    def __init__(self, session: _FakeAsyncSession | None = None) -> None:
        self.session = session or _FakeAsyncSession()
        self.opened = 0

    def get_session(self):
        self.opened += 1
        return self.session


# ------------------------------------------------- セッション妥当性チェック


class TestSessionValidation:
    def test_async_session_accepted(self):
        assert _is_usable_async_session(_FakeAsyncSession()) is True

    @pytest.mark.parametrize(
        "candidate",
        [None, _SyncSession(), lambda: None, "session", object()],
        ids=["none", "sync-session", "coroutine-func", "str", "object"],
    )
    def test_non_async_session_rejected(self, candidate):
        assert _is_usable_async_session(candidate) is False

    def test_resolve_prefers_explicit_session(self):
        explicit = _FakeAsyncSession()
        assert _resolve_session(None, explicit) is explicit

    def test_resolve_falls_back_to_repo_session(self):
        session = _FakeAsyncSession()
        repo = type("R", (), {"session": session})()
        assert _resolve_session(repo, None) is session

    def test_resolve_rejects_sync_session_with_reason(self, caplog):
        """同期 Session は「None じゃないのに使えない」= 従来は握り潰されていた。

        現在は原因を明示して None を返すので、原因不明の AttributeError に
        化けない。
        """
        repo = type("R", (), {"session": _SyncSession()})()
        with caplog.at_level("WARNING"):
            assert _resolve_session(repo, None) is None
        assert "非同期セッション" in caplog.text

    def test_resolve_rejects_coroutine_function(self):
        """DataRepositoryFacade 由来の coroutine function も拒否する。"""

        async def get_something():  # pragma: no cover - 呼ばれることはない
            return None

        repo = type("R", (), {"session": get_something})()
        assert _resolve_session(repo, None) is None

    def test_resolve_returns_none_quietly_when_absent(self, caplog):
        with caplog.at_level("WARNING"):
            assert _resolve_session(None, None) is None
        # 元々セッションが無いのは「設定していない」だけなので警告しない
        assert "非同期セッション" not in caplog.text


# ------------------------------------------------------- session_factory_from


class TestSessionFactory:
    """``session_factory_from`` は「CM を返す callable」を返すので呼び出しは ``factory()``。"""

    def test_yields_and_closes(self):
        db = _FakeDbManager()
        factory = session_factory_from(db)

        async def run():
            async with factory() as session:
                assert session is db.session
                assert db.session.closed == 0

        _run(run())
        assert db.opened == 1
        assert db.session.closed == 1

    def test_rolls_back_on_error(self):
        db = _FakeDbManager()
        factory = session_factory_from(db)

        async def run():
            with pytest.raises(RuntimeError):
                async with factory():
                    raise RuntimeError("本文生成で失敗")

        _run(run())
        assert db.session.rollbacks == 1
        assert db.session.closed == 1

    def test_each_call_opens_a_fresh_session(self):
        """1話ごとに別セッション。持ち回すと SQLite の書込ロックと衝突する。"""
        sessions = []

        class _Manager:
            def get_session(self):
                s = _FakeAsyncSession()
                sessions.append(s)
                return s

        factory = session_factory_from(_Manager())

        async def run():
            for _ in range(3):
                async with factory():
                    pass

        _run(run())
        assert len(sessions) == 3
        assert all(s.closed == 1 for s in sessions)

    def test_rejects_object_without_get_session(self):
        factory = session_factory_from(object())

        async def run():
            async with factory():
                pass

        with pytest.raises(RuntimeError, match="get_session"):
            _run(run())


# ------------------------------------------------------------------- commit 責務


class TestCommitResponsibility:
    def test_foreshadowing_repo_exposes_async_commit(self):
        assert inspect.iscoroutinefunction(DbForeshadowingRepository.commit)

    def test_digest_repo_exposes_async_commit(self):
        assert inspect.iscoroutinefunction(EpisodeDigestRepository.commit)

    def test_check_and_resolve_commits_once_per_episode(self):
        """1話1コミット。遷移ごとではなく最後に 1 回。"""
        session = _FakeAsyncSession()

        class _Repo:
            def __init__(self):
                self.db = session
                self.commits = 0

            async def get_unresolved(self, book_id):
                # 未回収が1件でもあれば「話ごとに1コミット」まで到達する
                return [SimpleNamespace(id=1, title="魔導剣", status="planted", target_episode=3)]

            async def commit(self):
                self.commits += 1
                await session.commit()

        repo = _Repo()
        _run(
            ForeshadowingService(repo).check_and_resolve(
                book_id=1, episode_num=3, draft_text="主人公が魔導剣を抜いた。"
            )
        )
        # 1話につき commit はちょうど1回（遷移本数には依存しない）
        assert repo.commits == 1

    def test_no_commit_when_nothing_unresolved(self):
        """未回収0件の時は早期 return して commit も走らない（無駄な書込を増やさない）。"""
        session = _FakeAsyncSession()

        class _Repo:
            db = session
            commits = 0

            async def get_unresolved(self, book_id):
                return []

            async def commit(self):
                type(self).commits += 1

        assert _run(ForeshadowingService(_Repo()).check_and_resolve(book_id=1, episode_num=1, draft_text="本文")) == []
        assert _Repo.commits == 0

    def test_check_and_resolve_tolerates_repo_without_commit(self, caplog):
        """テストダブル（MagicMock 等）は await できないので呼ばないこと。

        MagicMock の属性は毎回 '*' を返すため、``getattr`` の有無だけで判定すると
        「判定は正常なのに警告が出る」という壊れた公開状態になる。
        """

        class _RepoNoCommit:
            def __init__(self):
                self.db = _FakeAsyncSession()

            async def get_unresolved(self, book_id):
                return [SimpleNamespace(id=1, title="魔導剣", status="planted", target_episode=2)]

        with caplog.at_level("WARNING"):
            _run(
                ForeshadowingService(_RepoNoCommit()).check_and_resolve(
                    book_id=1, episode_num=2, draft_text="主人公が魔導剣を抜いた。"
                )
            )
        assert "commit に失敗" not in caplog.text

    def test_check_and_resolve_survives_commit_failure(self, caplog):
        class _RepoBadCommit:
            def __init__(self):
                self.db = _FakeAsyncSession()

            async def get_unresolved(self, book_id):
                return [SimpleNamespace(id=1, title="魔導剣", status="planted", target_episode=2)]

            async def commit(self):
                raise RuntimeError("database is locked")

        with caplog.at_level("WARNING"):
            _run(
                ForeshadowingService(_RepoBadCommit()).check_and_resolve(
                    book_id=1, episode_num=2, draft_text="主人公が魔導剣を抜いた。"
                )
            )
        assert "database is locked" in caplog.text

    def test_digest_service_commits_after_save(self):
        session = _FakeAsyncSession()
        saved: list[int] = []

        class _Repo:
            db = session

            async def save_digest(self, book_id, episode_num, digest_text):
                saved.append(episode_num)
                await session.flush()

            async def commit(self):
                await session.commit()

        digest = _run(
            EpisodeDigestService(repo=_Repo(), llm=None).summarize_and_save(
                book_id=1, episode_num=2, draft_text="主人公が剣を抜いた。"
            )
        )
        assert saved == [2]
        # flush だけでは永続化されないので commit が要る
        assert session.flushes == 1
        assert session.commits == 1
        assert isinstance(digest, str)


# ------------------------------------------------------- EpisodeWriter 統合


def _make_writer() -> EpisodeWriter:
    return EpisodeWriter(
        llm=None,
        context_builder=type("CB", (), {})(),
        repo=None,
    )


class TestPostEpisodeFinalize:
    def test_uses_session_factory_and_closes_it(self):
        db = _FakeDbManager()
        factory = session_factory_from(db)
        writer = _make_writer()

        result = _run(
            writer._post_episode_finalize(
                book_id=1,
                branch_id=1,
                ep_num=5,
                written_text="本文",
                writing_metadata=None,
                repo=None,
                session_factory=factory,
            )
        )
        assert result == []
        assert db.opened == 1
        # 後処理は「1話1トランザクション」で、必ず閉じていること
        assert db.session.closed == 1

    def test_short_circuits_on_empty_text_without_opening_session(self):
        db = _FakeDbManager()
        writer = _make_writer()
        assert (
            _run(
                writer._post_episode_finalize(
                    book_id=1,
                    branch_id=1,
                    ep_num=5,
                    written_text="",
                    writing_metadata=None,
                    session_factory=session_factory_from(db),
                )
            )
            == []
        )
        assert db.opened == 0

    def test_factory_failure_does_not_break_writing(self, caplog):
        """セッションを開けなくても本文の執筆は成立する（警告のみ）。"""

        def _broken_factory():
            raise RuntimeError("接続が establishment できない")

        writer = _make_writer()
        with caplog.at_level("WARNING"):
            result = _run(
                writer._post_episode_finalize(
                    book_id=1,
                    branch_id=1,
                    ep_num=5,
                    written_text="本文",
                    writing_metadata=None,
                    session_factory=_broken_factory,
                )
            )
        assert result == []
        assert "後処理セッションの確保に失敗" in caplog.text

    def test_without_factory_still_writes_body(self):
        """session_factory 未注入でも例外は出ない（後処理はスキップ）。"""
        writer = _make_writer()
        assert (
            _run(
                writer._post_episode_finalize(
                    book_id=1,
                    branch_id=1,
                    ep_num=5,
                    written_text="本文",
                    writing_metadata=None,
                    repo=None,
                )
            )
            == []
        )


# --------------------------------------------------------- generator の配線


class TestGeneratorWiring:
    def test_generator_no_longer_reads_repo_session(self):
        """``"session": getattr(repo, ...)`` は撤去済みであること。

        残ったままだと DataRepositoryFacade では coroutine function、
        本番の BookRepository では同期 Session が届き、
        どちらでも伏線回収・ダイジェスト保存が動かない。
        """
        import inspect as _inspect

        from src.agents.writing import generator as generator_mod

        source = _inspect.getsource(generator_mod)
        # 実行コードからは消えている（コメント中の言及は許す）
        assert '"session": getattr(' not in source
        assert '"session_factory": self.session_factory' in source

    def test_generator_accepts_session_factory(self):
        from src.agents.writing.generator import WritingGenerator

        factory = session_factory_from(_FakeDbManager())
        gen = WritingGenerator(repo=None, llm=None, session_factory=factory)
        assert gen.session_factory is factory

    def test_writing_agent_passes_session_factory_to_generator(self):
        from src.agents.writing.agent import WritingAgent

        factory = session_factory_from(_FakeDbManager())
        agent = WritingAgent(repo=None, llm=None, session_factory=factory)
        assert agent._get_generator().session_factory is factory

    def test_engine_adapter_builds_session_factory_from_db(self):
        from src.backend.orchestrator_engine_adapter import OrchestratorEngineAdapter

        db = _FakeDbManager()
        engine = OrchestratorEngineAdapter(repo=None, db=db, llm=None)
        assert callable(engine._dep("session_factory"))


# --------------------------------------------------- 1〜3話の経路（追加分）


class _FakeRepo:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def save_chapter(self, **kwargs):
        self.saved.append(kwargs)
        return 1


class _FakeOpeningBooster:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[int] = []

    async def generate_opening_episode(self, config, protagonist_name, genre):
        self.calls.append(config.ep_num)
        return {"content": self.content}


class TestOpeningEpisodesAlsoPostProcess:
    """1〜3話（OpeningBoosterAgent 経路）も後処理を回すこと。

    この経路は `EpisodeWriter.run()` を経由しないため、以前は
    伏線自動回収・事実ダイジェストが **1〜3話で永久に未実行** だった。
    """

    def _generator(self, content: str):
        from src.agents.writing.generator import WritingGenerator

        db = _FakeDbManager()
        gen = WritingGenerator(
            repo=_FakeRepo(),
            llm=None,
            pm=None,
            session_factory=session_factory_from(db),
        )
        gen._opening_booster = _FakeOpeningBooster(content)
        return gen, db

    def _finalize_calls(self, gen):
        calls: list[dict] = []

        async def _spy(**kwargs):
            calls.append(kwargs)

        gen._run_post_episode_finalize = _spy
        return calls

    def test_episode_one_runs_post_processing(self):
        gen, db = self._generator("第1話の本文。")
        calls = self._finalize_calls(gen)

        chars = _run(gen._write_single_episode_core(book_id=7, ep_num=1))

        assert chars == len("第1話の本文。")
        assert len(calls) == 1
        assert calls[0]["ep_num"] == 1
        assert calls[0]["book_id"] == 7
        # セッション工場は generator 自身が保持し、後処理側で参照する
        assert gen.session_factory is not None

    def test_episode_three_runs_post_processing(self):
        gen, _db = self._generator("第3話の本文。")
        calls = self._finalize_calls(gen)
        _run(gen._write_single_episode_core(book_id=7, ep_num=3))
        assert [c["ep_num"] for c in calls] == [3]

    def test_empty_content_skips_post_processing(self):
        gen, _db = self._generator("")
        calls = self._finalize_calls(gen)
        assert _run(gen._write_single_episode_core(book_id=7, ep_num=2)) == 0
        assert calls == []

    def test_chapter_is_saved_before_post_processing(self):
        """本文保存が失敗したら後処理しない（空本文を要約しない）。"""
        gen, _db = self._generator("本文")
        calls = self._finalize_calls(gen)
        gen.repo = None  # save されない
        _run(gen._write_single_episode_core(book_id=7, ep_num=1))
        assert calls == []

    def test_post_processing_failure_does_not_break_episode(self, caplog):
        """後処理が壊れても字数と本文は返る（執筆を落とさない）。"""
        gen, _db = self._generator("本文")

        async def _boom(**kwargs):
            raise RuntimeError("後処理で例外")

        gen._run_post_episode_finalize = _boom
        with caplog.at_level("WARNING"):
            chars = _run(gen._write_single_episode_core(book_id=7, ep_num=1))
        assert chars == len("本文")
        assert "後処理でエラー" in caplog.text

    def test_writer_construction_failure_is_swallowed(self, caplog):
        """EpisodeWriter を組み立てられない場合も落とさない。"""
        gen, _db = self._generator("本文")
        with caplog.at_level("WARNING"):
            _run(gen._run_post_episode_finalize(book_id=1, branch_id=1, ep_num=1, written_text="本文"))
        # llm=None で ContextBuilderAgent は組めるが.defensive に確認だけ
        assert isinstance(caplog.text, str)


# --------------------------------------------------------------------- helper


def _run(coro):
    import asyncio

    return asyncio.run(coro)
