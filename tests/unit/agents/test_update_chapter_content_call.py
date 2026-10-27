"""`update_chapter_content` が実シグネチャ通り呼ばれることの回帰テスト。

T6 Step 8 の回帰防止。

`ChapterRepository.update_chapter_content` の実シグネチャは
`(branch_id, ep_num, content)` だが、`src/agents/writing/agent.py` の
2 箇所は `chapter.id` を `branch_id` に、`rewritten_text` を `ep_num` に渡していた。
その結果 `content` が欠落し、**書き直しが TypeError で無言に失敗**していた
（`hasattr` ガードと広い `except` で表面化しない）。
"""

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.writing.agent import WritingAgent

AGENT_PY = Path("src/agents/writing/agent.py")


def _make_chapter(content: str = "元の本文", branch_id=None):
    return SimpleNamespace(id=999, content=content, branch_id=branch_id, ep_num=3)


def _make_agent(chapter):
    """`update_chapter_content` の呼び出しを記録する WritingAgent。"""
    repo = MagicMock()
    repo.get_chapter = AsyncMock(return_value=chapter)
    recorded: dict = {}
    repo.update_chapter_content = AsyncMock(
        side_effect=lambda *a, **k: recorded.update(args=a, kwargs=k)
    )
    agent = WritingAgent(repo=repo, llm=MagicMock())
    return agent, repo, recorded


# ── リポジトリ側の契約 ──────────────────────────────────────────


def test_repository_signature_is_stable():
    """リポジトリの実シグネチャが `(branch_id, ep_num, content)` であること。

    ここが変わったとき呼び出し側も変わるので、差異を早期に検出する。
    """
    from src.infrastructure.repositories.book import BookRepository
    from src.infrastructure.repositories.chapter import ChapterRepository

    for cls in (BookRepository, ChapterRepository):
        params = [
            p for p in inspect.signature(cls.update_chapter_content).parameters
            if p != "self"
        ]
        assert params[:3] == ["branch_id", "ep_num", "content"], (
            f"{cls.__name__}.update_chapter_content のシグネチャが変わった: {params}"
        )


# ── ソース構造の固定 ────────────────────────────────────────────


def test_no_call_passes_chapter_id_as_branch_id():
    """`chapter.id` を第1引数に渡す呼び出しが残っていないこと。"""
    tree = ast.parse(AGENT_PY.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update_chapter_content"
        ):
            if node.args and isinstance(node.args[0], ast.Attribute):
                if node.args[0].attr == "id":
                    offenders.append(node.lineno)
    assert not offenders, (
        f"`chapter.id` を branch_id に渡している呼び出しが残存: 行 {offenders}"
    )


def test_every_call_passes_three_positional_args():
    """全呼び出しが 3 つの位置引数を持つこと（`content` 欠落の防止）。"""
    tree = ast.parse(AGENT_PY.read_text(encoding="utf-8"))
    counts = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update_chapter_content"
        ):
            counts.append((node.lineno, len(node.args)))
    assert counts, "update_chapter_content の呼び出しが無い"
    for lineno, n in counts:
        assert n == 3, (
            f"{AGENT_PY}:{lineno} が {n} 個の位置引数で呼んでいる"
            "（`content` が欠落している）"
        )


# ── 実挙動 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rewrite_for_dimension_passes_correct_args():
    """`rewrite_for_dimension` が (branch_id, ep_num, content) で呼ぶこと。"""
    chapter = _make_chapter(branch_id=7)
    agent, repo, recorded = _make_agent(chapter)

    await agent.rewrite_for_dimension(
        book_id=1, branch_id=7, ep_num=3, dimension="tone",
    )

    assert recorded, "update_chapter_content が呼ばれなかった"
    args = recorded.get("args", ())
    assert args[0] == 7, f"branch_id が違う: {args[0]}"
    assert args[1] == 3, f"ep_num が違う: {args[1]}"
    assert isinstance(args[2], str) and args[2], f"content が文字列でない: {args[2]!r}"


@pytest.mark.asyncio
async def test_rewrite_with_focus_uses_chapter_branch_id():
    """`rewrite_with_focus` は章の branch_id を使うこと（引数が無いため）。"""
    chapter = _make_chapter(branch_id=42)
    agent, repo, recorded = _make_agent(chapter)

    await agent.rewrite_with_focus(book_id=1, ep_num=3, focus="enhance_hook")

    assert recorded, "update_chapter_content が呼ばれなかった"
    args = recorded.get("args", ())
    assert args[0] == 42, f"branch_id が chapter.branch_id になっていない: {args[0]}"
    assert args[1] == 3
    assert isinstance(args[2], str) and args[2]


@pytest.mark.asyncio
async def test_rewrite_with_focus_falls_back_to_branch_one():
    """章が branch_id を保持しない場合は get_chapter(1, ...) と同じ 1 を使う。"""
    chapter = _make_chapter(branch_id=None)
    agent, repo, recorded = _make_agent(chapter)

    await agent.rewrite_with_focus(book_id=1, ep_num=3, focus="enhance_hook")

    args = recorded.get("args", ())
    assert args[0] == 1, f"フォールバック値が 1 でない: {args[0]}"
    assert args[1] == 3
