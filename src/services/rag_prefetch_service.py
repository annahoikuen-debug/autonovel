"""
RAG Prefetch Service - プロット確定時にRAG検索を先行実行し、
結果をメモリにキャッシュするサービス。

v4.0: 執筆時のRAG検索待ち時間をゼロにする先行キャッシュ基盤
v6.0 / PLAN_W6: 投機実行の静的限定（`static_only`）と全経路での即時キャンセル対応。
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Any

from src.services.prefetch.registry import PrefetchRegistry

logger = logging.getLogger(__name__)

#: 全インスタンス共通のタスクレジストリ。
#: `RagPrefetchService()` は呼び出しごとに生成されるため、書籍単位の取り消しを
#: 効かせるにはレジストリがインスタンスをまたいで共有されている必要がある。
_SHARED_REGISTRY = PrefetchRegistry()


async def _null(value: Any) -> Any:
    """機能が無い engine 用に空結果を返すだけの no-op コルーチン。

    v5.3 までは `asyncio.coroutine(lambda: X)()` を使っていたが、
    `asyncio.coroutine` は **Python 3.11 で削除済み**のため、
    engine に該当機能が無いと同期的に `AttributeError` が起き、
    `_do_prefetch` 末尾の一括 `except` に落ちて **プリフェッチが恒久 no-op** になっていた。
    """
    return value


class RagPrefetchService:
    """プロット確定時にRAG検索結果を先行キャッシュする。

    プロットが確定した時点で、執筆に必要な以下の3種類のRAG検索を
    バックグラウンドで並列実行し、結果をメモリにキャッシュする:
    1. スタイルサンプル検索（文体RAG）
    2. 過去ログからの関連コンテキスト検索
    3. プロジェクトインテリジェンス
    """

    def __init__(self, max_cache_size: int = 50):
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._max_cache_size = max_cache_size
        self._pending_tasks: dict[str, asyncio.Task] = {}
        # PLAN_W6 Step 1/5: タスクのハンドル管理を 1 か所に寄せる。
        # `_pending_tasks` は後方互換のため残す（既存テストと `get_cached` が参照する）。
        self._registry = _SHARED_REGISTRY
        #: `static_only=True` で投入されたキーの集合（payload に `"static": True` を付けるため）。
        self._static_keys: set[str] = set()

    def cache_key(self, book_id: int, ep_num: int) -> str:
        return f"{book_id}_{ep_num}"

    async def prefetch_for_episode(
        self,
        engine: Any,
        book_id: int,
        branch_id: int,
        ep_num: int,
        plot_blueprint: str,
        static_only: bool = False,
    ) -> None:
        """プロット確定直後に呼び出す。RAG検索をバックグラウンドで開始する。

        Args:
            engine: UltimateHegemonyEngine インスタンス
            book_id: 作品ID
            branch_id: ブランチID
            ep_num: エピソード番号
            plot_blueprint: プロットの設計図テキスト（検索クエリとして使用）
            static_only: True のとき **静的ナレッジのみ** を対象とする。
                World Memory / Character Memory のように 1 話の進行に依らない
                ナレッジを事前ロードする用途。既定は False（既存挙動を変えない）。
        """
        key = self.cache_key(book_id, ep_num)
        if key in self._cache or key in self._pending_tasks:
            return

        if static_only:
            # 静的ナレッジのみを温めるので、引数の hash を含めないキーを使う。
            self._static_keys.add(key)

        from src.core.async_utils import fire_and_forget

        task = fire_and_forget(
            self._do_prefetch(engine, book_id, branch_id, ep_num, plot_blueprint),
            name=f"prefetch_ep_{ep_num}",
        )
        self._pending_tasks[key] = task
        # ハンドル保持はレジストリに集約する（cancel / cancel_prefix の入口を 1 か所にする）。
        self._registry.track(key, task)

    async def _do_prefetch(
        self, engine: Any, book_id: int, branch_id: int, ep_num: int, blueprint: str
    ) -> None:
        """バックグラウンドで3種類のRAG検索を並列実行する"""
        key = self.cache_key(book_id, ep_num)
        try:
            tasks = []

            # 1. スタイルRAG検索
            if hasattr(engine, "style_rag") and engine.style_rag:
                tasks.append(
                    engine.style_rag.find_best_samples(
                        scene_description=blueprint, phase="Prep", top_k=3
                    )
                )
            else:
                tasks.append(_null([]))

            # 2. 過去ログRAG検索
            if hasattr(engine, "repo") and hasattr(engine.repo, "get_relevant_past_logs"):
                tasks.append(
                    engine.repo.get_relevant_past_logs(
                        branch_id, ep_num, query_text=blueprint, book_id=book_id
                    )
                )
            else:
                tasks.append(_null(""))

            # 3. プロジェクトインテリジェンス
            if hasattr(engine, "get_project_intelligence"):
                tasks.append(engine.get_project_intelligence(book_id, context=blueprint))
            else:
                tasks.append(_null({}))

            from src.core.async_utils import run_parallel

            results = await run_parallel(tasks, return_exceptions=True)

            style_samples = results[0] if not isinstance(results[0], Exception) else []
            rag_ctx = results[1] if not isinstance(results[1], Exception) else ""
            intel = results[2] if not isinstance(results[2], Exception) else {}

            self._cache[key] = {
                "style_samples": style_samples,
                "rag_context": rag_ctx,
                "intelligence": intel,
                "prefetched": True,
            }
            if key in self._static_keys:
                self._cache[key]["static"] = True

            # LRU: 古いキャッシュを破棄
            while len(self._cache) > self._max_cache_size:
                self._cache.popitem(last=False)

            logger.info(f"[RAG PREFETCH] Ep.{ep_num} prefetched successfully")
        except Exception as e:
            logger.warning(f"[RAG PREFETCH] Ep.{ep_num} _do_prefetch failed: {e}")
        finally:
            self._pending_tasks.pop(key, None)
            self._static_keys.discard(key)

    async def get_cached(self, book_id: int, ep_num: int) -> dict[str, Any] | None:
        """キャッシュされたRAG結果を取得。未完了のタスクがあれば待機する。"""
        key = self.cache_key(book_id, ep_num)

        # 進行中のタスクがあれば待機
        if key in self._pending_tasks:
            try:
                await self._pending_tasks[key]
            except Exception:
                pass

        result = self._cache.get(key)
        if result:
            logger.info(f"[RAG CACHE HIT] Ep.{ep_num}")
        return result

    def invalidate(self, book_id: int, ep_num: int) -> None:
        """指定エピソードのキャッシュを無効化する"""
        key = self.cache_key(book_id, ep_num)
        self._cache.pop(key, None)
        # 進行中のタスクもキャンセル
        task = self._pending_tasks.pop(key, None)
        self._registry.untrack(key)
        if task and not task.done():
            task.cancel()

    async def cancel_all(self) -> int:
        """進行中のプリフェッチを全て取り消す（PLAN_W6 Step 6）。

        書籍単位の切り分けは `cancel_book` / `routers/episodes.py` のリトライ経路が担う。
        実際に取り消した本数を返す。例外は送出しない（ログのみ）。
        """
        targets: list[asyncio.Task] = []
        for key in list(self._pending_tasks):
            # ハンドル管理はレジストリ側に一本化しているため、登録だけ外す。
            self._registry.untrack(key)
            task = self._pending_tasks.pop(key, None)
            if task is None or task.done():
                continue
            task.cancel()
            targets.append(task)
        if targets:
            await asyncio.gather(*targets, return_exceptions=True)
            logger.info("[RAG PREFETCH] cancelled %d pending prefetch task(s)", len(targets))
        return len(targets)

    async def cancel_book(self, book_id: int) -> int:
        """指定書籍の進行中プリフェッチのみを取り消す。"""
        return await self._registry.cancel_prefix(str(book_id))

    async def close(self) -> None:
        """取り消しの上、キャッシュも捨てる。"""
        await self.cancel_all()
        self._cache.clear()
        self._static_keys.clear()

    def get_stats(self) -> dict[str, Any]:
        """キャッシュの統計情報を返す"""
        return {
            "cached_episodes": len(self._cache),
            "pending_tasks": len(self._pending_tasks),
            "max_size": self._max_cache_size,
            "keys": list(self._cache.keys()),
        }
