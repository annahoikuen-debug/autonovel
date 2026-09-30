"""tests/regression/test_v53_wiring_reachability.py.

v5.3 で追加した長編耐性の配線（伏線自動回収・契約伏線プロンプト・3層記憶）が
**本番経路で実際に到達可能か**を実行時に計測するリグレッション防止テスト。

背景:
    v5.3 の実装は「書いたが呼ばれていない」状態だった。主な断点は以下の4点:
      (a) ``EpisodeWriter.run()`` が呼ばれず、伏線自動回収とダイジェスト永続化
          が未実行（``generator.py:141`` は ``write()`` を直接呼ぶ）
      (b) ``use_beat_to_scene`` 既定 True のため、最終書き込みプロンプト
          （``build_final_writing_prompt``）に到達しない
      (c) ``ContextBuilderAgent.execute`` が ``repo`` 不在で早期 return し、
          ``writing_context`` が空のまま
      (d) ``BookRepository`` に執筆エージェントが必要とする章操作メソッドが無く、
          本番執筆が ``AttributeError`` で失敗する

このテストは上記4点を**機械的に検証**する。
``TARGETS`` が「Phase A 完了後に期待する状態」を表す。
Step 6〜11 の完了時に TARGETS を True へ反転させること。
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

SRC = ROOT_DIR / "src"


# ── Phase A 完了後に期待する状態 ────────────────────────────────
# Step 6〜11 の完了.flip させる。
TARGETS: dict[str, bool] = {
    # Step 7 完了: generator.py が writer.run() 経由で生成する
    "episode_writer_run_reachable": True,
    # Step 8 完了: beat-to-scene 経路でも伏線処理が走る
    "final_writing_prompt_reachable": True,
    # Step 9 完了: build_scene_context が repo/session を渡す
    "context_builder_receives_repo": True,
    # Step 6 完了（C0 解消）: BookRepository が章操作・聖書読み出しを提供する
    "repository_chapter_contract_satisfied": True,
    # Step 10 完了: session.execute は await 統一、build_context は常に coroutine
    "session_type_await_consistent": True,
    "build_context_await_consistent": True,
}


def _repo_calls_in(relative_path: str) -> set[str]:
    """``self.repo.<method>(...)`` のメソッド名集合を静的抽出する。"""
    tree = ast.parse((SRC / relative_path).read_text("utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "repo"
        ):
            found.add(node.func.attr)
    return found


class TestRepositoryContract:
    """(d) 執筆エージェントが必要とする章操作が ``BookRepository`` で充足されるか。"""

    def test_generator_calls_are_satisfied(self) -> None:
        from src.infrastructure.repositories.book import BookRepository

        called = _repo_calls_in("agents/writing/generator.py")
        assert called, "generator.py で self.repo.* の呼び出しが見つからない（解析前提の変化）"
        missing = sorted(m for m in called if not hasattr(BookRepository, m))
        assert missing is not TARGETS["repository_chapter_contract_satisfied"] or not missing, (
            f"BookRepository に存在しないメソッドを呼んでいる: {missing}"
            f"（expected_missing={missing if not TARGETS['repository_chapter_contract_satisfied'] else []}）"
        ) if TARGETS["repository_chapter_contract_satisfied"] else bool(missing) is False or None
        assert (not missing) is TARGETS["repository_chapter_contract_satisfied"], (
            f"generator.py が呼ぶ repo メソッドの欠損状態が想定と不一致: missing={missing}"
        )

    def test_agent_calls_are_satisfied(self) -> None:
        from src.infrastructure.repositories.book import BookRepository

        called = _repo_calls_in("agents/writing/agent.py")
        assert called, "agent.py で self.repo.* の呼び出しが見つからない（解析前提の変化）"
        missing = sorted(m for m in called if not hasattr(BookRepository, m))
        assert (not missing) is TARGETS["repository_chapter_contract_satisfied"], (
            f"agent.py が呼ぶ repo メソッドの欠損状態が想定と不一致: missing={missing}"
        )

    def test_chapter_repository_provides_the_primitives(self) -> None:
        """委譲先 ``ChapterRepository`` がプリミティブを持つこと（前提の固定）。"""
        from src.infrastructure.repositories.chapter import ChapterRepository

        for name in ("create_chapter", "get_chapter", "update_chapter_content"):
            assert hasattr(ChapterRepository, name), f"ChapterRepository に {name} が無い"

    def test_bible_repository_provides_get_latest_bible(self) -> None:
        from src.infrastructure.repositories.bible import BibleRepository

        assert hasattr(BibleRepository, "get_latest_bible")


class TestEpisodeWriterRunReachability:
    """(a) ``EpisodeWriter.run()`` に伏線自動回収とダイジェスト永続化があるか。"""

    def test_run_contains_foreshadowing_auto_resolve(self) -> None:
        # run() は共通後処理に委譲する（Step 8 で _post_episode_finalize に集約）
        from src.agents.writing.episode_writer import EpisodeWriter

        src = inspect.getsource(EpisodeWriter.run)
        assert "_post_episode_finalize" in src, "EpisodeWriter.run に共通後処理が無い"

    def test_run_contains_digest_persistence(self) -> None:
        from src.agents.writing.episode_writer import EpisodeWriter

        # ダイジェスト永続化は _post_episode_finalize 内に集約されている
        finalize_src = inspect.getsource(EpisodeWriter._post_episode_finalize)
        assert "_persist_episode_digest" in finalize_src, (
            "共通後処理にダイジェスト永続化が無い"
        )

    def test_generator_calls_run(self) -> None:
        """``generator.py`` が ``writer.run()`` 経由で生成する経路を持つこと。"""
        tree = ast.parse((SRC / "agents" / "writing" / "generator.py").read_text("utf-8"))
        calls_run = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "writer"
            for node in ast.walk(tree)
        )
        assert calls_run is TARGETS["episode_writer_run_reachable"], (
            "generator.py が writer.run() を呼ぶ状態が想定と不一致"
        )


class TestBeatToSceneWiring:
    """(b) beat-to-scene が既定経路であることと、その配線先の存在。"""

    def test_beat_to_scene_is_the_default(self) -> None:
        """既定の執筆分岐が beat-to-scene であることを固定する（Step 8 の前提）。"""
        from src.agents.writing.generator import WritingGenerator

        assert '"use_beat_to_scene": True' in inspect.getsource(WritingGenerator), (
            "beat-to-scene 既定という前提がPlans 通りでない。Step 8 の前提を再確認すること"
        )

    def test_beat_to_scene_handler_exists(self) -> None:
        from src.agents.writing.episode_writer import EpisodeWriter

        assert hasattr(EpisodeWriter, "write_beat_to_scene")

    def test_beat_to_scene_wired_to_foreshadowing(self) -> None:
        """beat-to-scene 経路が伏線回収まで配線されているか（Step 8 の完了判定）。

        T6 Step 1 以降、後処理の**実行点は `run()` の1箇所のみ**に集約されている
        （`write_beat_to_scene()` と `run()` の両方から呼ぶと、1話1回の
        ブロッキング LLM 呼出であるダイジェスト生成が話ごとに2回走る）。
        したがって「`run()` から到達であること」と
        「`write_beat_to_scene()` からは二重に呼ばれないこと」の両方を検証する。
        """
        from src.agents.writing.episode_writer import EpisodeWriter

        run_src = inspect.getsource(EpisodeWriter.run)
        assert "_post_episode_finalize" in run_src, (
            "`run()` が唯一の実行点として後処理を呼び出していない"
        )

        beat_src = inspect.getsource(EpisodeWriter.write_beat_to_scene)
        assert "_post_episode_finalize" not in beat_src, (
            "`write_beat_to_scene()` からも呼ぶと1話2回になり、"
            "ダイジェスト生成のコストが2倍になる"
        )

        # `write()` は `use_beat_to_scene` の両分岐で `run()` へ到達する前提であること
        write_src = inspect.getsource(EpisodeWriter.write)
        assert "write_beat_to_scene" in write_src, (
            "`write()` が `write_beat_to_scene()` へ委譲していない。"
            "T6 Step 1 の単一実行点では、既定分岐が `run()` を素通りする"
        )


class TestContextBuilderContract:
    """(c) ``ContextBuilderAgent`` が本番 repo/session を受け取れるか。"""

    def test_scene_writer_passes_repo_in_artifacts(self) -> None:
        from src.agents.writing.scene_writer import SceneWriter

        src = inspect.getsource(SceneWriter.build_scene_context)
        has_repo = '"repo"' in src or "'repo'" in src
        has_session = '"session"' in src or "'session'" in src
        assert (has_repo and has_session) is TARGETS["context_builder_receives_repo"], (
            f"build_scene_context の artifacts 供給状態が想定と不一致"
            f" (repo={has_repo}, session={has_session})"
        )

    def test_scene_writer_accepts_repo_at_construction(self) -> None:
        # SceneWriter は既に repo を受け取る（前提の固定）
        from src.agents.writing.scene_writer import SceneWriter

        assert "repo" in inspect.signature(SceneWriter.__init__).parameters

    def test_context_builder_requires_repo_guard_exists(self) -> None:
        """repo 不在で早期 return するガードが存在すること（前提の固定）。"""
        from src.agents.context_builder_agent import ContextBuilderAgent

        assert "repo is required in artifacts" in inspect.getsource(
            ContextBuilderAgent.execute
        )


class TestSessionTypeContract:
    """C2: 同期/非同期セッションの排他要件が解消されているか。"""

    def test_context_builder_session_await_is_consistent(self) -> None:
        """``ContextBuilderAgent`` 内で await 無しの ``session.execute`` が無いこと。

        ``SessionLocal`` は同期 ``sessionmaker`` であり、非同期リポジトリ
        （``DbForeshadowingRepository`` 等）が受け取る ``AsyncSession`` とは
        排他である。1つのクラスに両者を同居させない。
        """
        from src.agents.context_builder_agent import ContextBuilderAgent

        src = inspect.getsource(ContextBuilderAgent)
        unawaited = src.count("= session.execute(")
        awaited = src.count("await session.execute(")
        consistent = unawaited == 0
        assert consistent is TARGETS["session_type_await_consistent"], (
            f"session.execute の await 不整合（await 付き {awaited} / await 無し {unawaited}）"
        )

    def test_build_context_is_awaitable_even_without_db(self) -> None:
        # build_context は db is None でも coroutine を返すこと（M7）
        # 現状は dict を返すため、呼び出し側の await が TypeError になる
        import asyncio

        from src.services.episode_context import EpisodeContextBuilder

        builder = EpisodeContextBuilder(db=None)
        result = EpisodeContextBuilder.build_context(builder, book_id=1, ep_num=2)
        is_awaitable = asyncio.iscoroutine(result)
        if is_awaitable:
            result.close()
        assert is_awaitable is TARGETS["build_context_await_consistent"], (
            f"db=None のとき build_context が coroutine を返さない: {type(result)}"
        )


class TestDiagnosticsSnapshot:
    """TARGETS 定義自体の整合性（Phase A 完了時の反転を易于にする）。"""

    @pytest.mark.parametrize("key", sorted(TARGETS))
    def test_target_is_bool(self, key: str) -> None:
        assert key in TARGETS and isinstance(TARGETS[key], bool)
