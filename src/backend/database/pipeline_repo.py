"""統合パイプラインステップが使う「旧リポジトリ API」の互換アダプタ。

``src/services/pipeline_steps.py`` は以下のように**名前を続けて**リポジトリを叩く::

    engine.repo.plot.get_all_plots(1, book_id=book_id)
    engine.repo.bible.get_by_book_id(book_id)
    engine.repo.episode.get_by_book_and_number(book_id, ep_num)
    engine.repo.episode.update_content(book_id, ep_num, content)
    engine.repo.chapters.get_all_non_anchor_chapters(book_id)

ところが ``DataRepositoryFacade.__getattr__`` は**メソッド名**だけを解決する
flat な委譲なので、``repo.plot`` は coroutine 関数（``wrapper``）を返し、
``.get_all_plots`` で ``AttributeError`` になる。実在するリポジトリにも
``get_by_book_and_number`` / ``update_content`` というメソッドは無い
（正しくは ``get_chapter(branch_id, ep_num, book_id)`` /
``update_chapter_content(branch_id, ep_num, content, book_id)``）。

このモジュールは ``DataRepositoryFacade`` を素通ししつつ、上記の名前と
シグネチャだけを追加する薄いシェルを返す。ステップ本体を書き換えずに
パイプラインを動かせるようにするのが目的。

``branch_id`` は作品間で共有される既定値 1 なので、取り引きはすべて
``book_id`` も条件にすること（他作品の本編が混ざる）。

なお ``repo.session`` は素通しされない。``DataRepositoryFacade`` が
セッションを保持しないため coroutine 関数が返り、``EpisodeWriter`` の
伏線回収・事実ダイジェスト保存（``repo.session`` を直接使う）は
``'function' object has no attribute 'execute'`` でスキップされる。
長さ持ちセッションを足すと UnitOfWork の並列トランザクションと SQLite の
書き込みロックが衝突して全話分が "database is locked" で失敗するため、
代わりに :func:`session_factory_from` が **後処理の直前だけ開く短い
セッション**を供給する。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_BRANCH_ID = 1

__all__ = ["PipelineRepoCompat", "wrap_repo", "session_factory_from"]


def session_factory_from(db: Any) -> Callable[[], Any]:
    """1話ごとに「短いトランザクション」を開くセッションファクトリを返す。

    ``DbForeshadowingRepository`` / ``EpisodeDigestRepository`` は
    ``await self.db.flush()`` で終わるため **非同期セッション**が要る。しかし
    セッションを 1 つ持ち回すと、SQLite（WAL でも書込は1本）が他経路の
    コミットと衝突する。よって **書き込みが必要な後処理の直前だけ**開き、
    ``finally`` で必ず閉じる短いスコープにするのが正しい。

    戻り値は ``async with factory() as session:`` で使える。

    Args:
        db: ``DatabaseManager``（``get_session()`` を持つオブジェクト）。

    Returns:
        ``async with factory() as session:`` で使える async CM ファクトリ。

    Raises:
        RuntimeError: ``db`` が ``get_session()`` を持たない場合（設定ミス）。
    """

    @asynccontextmanager
    async def _scope() -> AsyncIterator[Any]:
        get_session = getattr(db, "get_session", None)
        if get_session is None:
            raise RuntimeError(
                f"session_factory_from() には get_session() を持つ DatabaseManager が"
                f"必要ですが、{type(db).__name__} が渡されました。"
            )
        session = get_session()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            # close() しないと aiosqlite の接続がプールに戻らず、プロセス終了時に
            # "greenlet is being finalized" で大量のノイズが出る。
            await session.close()

    return _scope


class _PlotCompat:
    """``repo.plot.*`` 互換。"""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def get_all_plots(self, branch_id: int = DEFAULT_BRANCH_ID, book_id: int | None = None) -> list[Any]:
        return await self._inner.get_all_plots(book_id_or_branch_id=branch_id, branch_id=branch_id, book_id=book_id)

    async def get_by_book_and_number(self, book_id: int, ep_num: int) -> Any:
        return await self._inner.get_plot(book_id, ep_num, branch_id=DEFAULT_BRANCH_ID, book_id=book_id)


class _BibleCompat:
    """``repo.bible.*`` 互換。"""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def get_by_book_id(self, book_id: int) -> Any:
        return await self._inner.get_latest_bible(book_id)


class _EpisodeCompat:
    """``repo.episode.*`` 互換（実体は chapters リポジトリ）。"""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def get_by_book_and_number(self, book_id: int, ep_num: int) -> Any:
        return await self._inner.get_chapter(DEFAULT_BRANCH_ID, ep_num, book_id=book_id)

    async def get_all_by_book_id(self, book_id: int) -> list[Any]:
        return await self._inner.get_all_non_anchor_chapters(book_id, DEFAULT_BRANCH_ID)

    async def update_content(self, book_id: int, ep_num: int, content: str) -> int:
        return await self._inner.update_chapter_content(DEFAULT_BRANCH_ID, ep_num, content, book_id=book_id)


class _ChaptersCompat:
    """``repo.chapters.*`` 互換。"""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def get_all_non_anchor_chapters(self, book_id: int, branch_id: int | None = None) -> list[Any]:
        return await self._inner.get_all_non_anchor_chapters(book_id, branch_id)


class PipelineRepoCompat:
    """``DataRepositoryFacade`` に旧名前を足したラッパー。"""

    def __init__(self, inner: Any) -> None:
        object.__setattr__(self, "_inner", inner)

    def __getattr__(self, name: str) -> Any:
        # 未定義属性は内側のファサード（get_book / save_chapter / ...）へ素通しする。
        return getattr(object.__getattribute__(self, "_inner"), name)

    @property
    def inner(self) -> Any:
        return object.__getattribute__(self, "_inner")

    @property
    def plot(self) -> _PlotCompat:
        return _PlotCompat(self.inner)

    @property
    def bible(self) -> _BibleCompat:
        return _BibleCompat(self.inner)

    @property
    def episode(self) -> _EpisodeCompat:
        return _EpisodeCompat(self.inner)

    @property
    def chapters(self) -> _ChaptersCompat:
        return _ChaptersCompat(self.inner)


def wrap_repo(repo: Any) -> Any:
    """既に互換シェルならそのまま返す。それ以外は包む。"""
    if isinstance(repo, PipelineRepoCompat):
        return repo
    if repo is None:
        return None
    return PipelineRepoCompat(repo)
