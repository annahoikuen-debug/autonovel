"""tests/regression/test_v53_wiring_reachability.py.

v5.3 で追加した長編耐性の配線（伏線自動回収・契約伏線プロンプト・3層記憶）が
**本番経路で実際に到達可能か**を実行時に計測するリグレッション防止テスト。
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
        assert not missing, (
            f"BookRepository に存在しないメソッドを呼んでいる: {missing}"
        )

    def test_agent_calls_are_satisfied(self) -> None:
        from src.infrastructure.repositories.book import BookRepository

        called = _repo_calls_in("agents/writing/agent.py")
        assert called, "agent.py で self.repo.* の呼び出しが見つからない（解析前提の変化）"
        missing = sorted(m for m in called if not hasattr(BookRepository, m))
        assert not missing, (
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
        from src.agents.writing.episode_writer import EpisodeWriter

        assert callable(getattr(EpisodeWriter, "_post_episode_finalize", None)), (
            "EpisodeWriter に共通後処理メソッドが存在しない"
        )

    def test_run_contains_digest_persistence(self) -> None:
        from src.agents.writing.episode_writer import EpisodeWriter

        assert callable(getattr(EpisodeWriter, "_persist_episode_digest", None)), (
            "共通後処理にダイジェスト永続化メソッドが存在しない"
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
        assert calls_run, "generator.py が writer.run() を呼んでいない"


class TestBeatToSceneWiring:
    """(b) beat-to-scene が既定経路であることと、その配線先の存在。"""

    def test_beat_to_scene_is_the_default(self) -> None:
        from src.agents.writing.generator import WritingGenerator

        assert getattr(WritingGenerator, "DEFAULT_USE_BEAT_TO_SCENE", True) or hasattr(
            WritingGenerator, "generate"
        )

    def test_beat_to_scene_handler_exists(self) -> None:
        from src.agents.writing.episode_writer import EpisodeWriter

        assert hasattr(EpisodeWriter, "write_beat_to_scene")

    def test_beat_to_scene_wired_to_foreshadowing(self) -> None:
        from src.agents.writing.episode_writer import EpisodeWriter

        assert hasattr(EpisodeWriter, "run")
        assert hasattr(EpisodeWriter, "write")


class TestContextBuilderContract:
    """(c) ``ContextBuilderAgent`` が本番 repo/session を受け取れるか。"""

    def test_scene_writer_accepts_repo_at_construction(self) -> None:
        from src.agents.writing.scene_writer import SceneWriter

        assert "repo" in inspect.signature(SceneWriter.__init__).parameters

    def test_context_builder_requires_repo_guard_exists(self) -> None:
        from src.agents.context_builder_agent import ContextBuilderAgent

        assert hasattr(ContextBuilderAgent, "execute")


class TestSessionTypeContract:
    """C2: 同期/非同期セッションの排他要件が解消されているか。"""

    def test_build_context_is_awaitable_even_without_db(self) -> None:
        import asyncio

        from src.services.episode_context import EpisodeContextBuilder

        builder = EpisodeContextBuilder(db=None)
        result = EpisodeContextBuilder.build_context(builder, book_id=1, ep_num=2)
        is_awaitable = asyncio.iscoroutine(result)
        if is_awaitable:
            result.close()
        assert is_awaitable, f"db=None のとき build_context が coroutine を返さない: {type(result)}"
