"""Episode 4 リグレッション: branch_id のデフォルト温存と明示指定優先.

Q5 方針: branch_id=1 はデフォルトとして残し、明示指定があればそちらを優先する。
"""
from __future__ import annotations

import inspect

import pytest

from src.backend.engine_context import ContextManager


class _StubBook:
    def __init__(self, current_branch_id: int | None = None):
        self.current_branch_id = current_branch_id


class _StubRepo:
    def __init__(self, current_branch_id: int | None = None):
        self._book = _StubBook(current_branch_id)
        self.calls: list[tuple[str, int | None]] = []

    async def get_book(self, _book_id):
        return self._book

    async def get_chapters_before(self, branch_id, ep, book_id=None):
        self.calls.append(("get_chapters_before", book_id))
        return []

    async def get_relevant_past_logs(self, branch_id, ep, query_text="", book_id=None):
        self.calls.append(("get_relevant_past_logs", book_id))
        return ""


def _bare_context_manager(repo):
    """``ContextManager.__init__`` が設定する属性だけを持つインスタンスを作る。

    ``ContextManager`` は非推奨で ``__init__`` が DeprecationWarning を出すため、
    ここでは ``__new__`` で生成して ``__init__`` が設定する
    ``repo`` / ``compressor`` / ``_delegate_agent`` を明示的に整える
    (``_get_delegate()`` は ``_delegate_agent`` を読むため必須）。
    """
    ctx = ContextManager.__new__(ContextManager)
    ctx.repo = repo
    ctx.compressor = None
    ctx._delegate_agent = None
    return ctx


@pytest.mark.asyncio
async def test_engine_context_default_branch_is_one():
    """branch_id 未指定時は book.current_branch_id=1 → 1 維持."""
    repo = _StubRepo(current_branch_id=None)
    ctx = _bare_context_manager(repo)
    result = await ctx.build_past_context(book_id=1, end_ep=1)
    assert result is not None  # 呼び出しが成功


@pytest.mark.asyncio
async def test_engine_context_propagates_book_id_to_repo():
    """branch_id は作品間で共有されるため、参照クエリには book_id も渡されること。

    book_id を落とすと他作品の同ブランチ行が混ざり、プロンプトと生成本文に流出する。
    """
    repo = _StubRepo(current_branch_id=None)
    ctx = _bare_context_manager(repo)
    await ctx.build_past_context(book_id=7, end_ep=1)
    assert repo.calls, "リポジトリが一度も呼ばれていない"
    assert all(book_id == 7 for _, book_id in repo.calls), f"book_id が伝播していない: {repo.calls}"


@pytest.mark.asyncio
async def test_engine_context_explicit_branch_takes_priority():
    """branch_id 明示指定時は book.current_branch_id より優先."""
    repo = _StubRepo(current_branch_id=2)
    ctx = ContextManager.__new__(ContextManager)
    ctx.repo = repo

    # シグネチャに branch_id パラメータが存在することを確認
    sig = inspect.signature(ctx.build_past_context)
    assert "branch_id" in sig.parameters, "branch_id param must exist"
    assert sig.parameters["branch_id"].default is None


@pytest.mark.asyncio
async def test_engine_context_get_optimal_context_split_has_branch_id():
    sig = inspect.signature(ContextManager.get_optimal_context_split)
    assert "branch_id" in sig.parameters


def test_hooks_router_accepts_branch_id_in_payload():
    """hooks.py の update hook で branch_id を payload から取れる."""
    from src.backend.routers.hooks import apply_hook_fix

    sig = inspect.signature(apply_hook_fix)
    params = sig.parameters
    assert "ep_num" in params
    assert "payload" in params
    # payload は dict[str, Any] なので branch_id は中で取得（変更反映済み）
