"""投機的プリフェッチタスクの共通レジストリ（PLAN_W6 Step 1）。

## なぜ要るのか

W6 実害の本体は「遅い」ことではなく **「無駄な課金が静かに続ける」** ことである。
背景タスクのハンドル管理は3系統に分かれており、**どれもキャンセル不能**だった。

| 系統 | 置き場 | 問題 |
|---|---|---|
| `semantic_cache._BACKGROUND_TASKS` | `set[Task]` | キー無し。どれを殺すべきか判定できない |
| `RagPrefetchService._pending_tasks` | `dict[str, Task]` | `invalidate` の呼び出し元がゼロ |
| `workflow._trigger_prefetch` | `asyncio.create_task` | ハンドル自体が無い |

本クラスは **cancel_all / cancel_prefix / cancel / stats** だけを持つ薄い共通点であり、
以降のステップ（Step 3〜12）はすべてこの 1 か所だけを触ればよくなる。

## 設計方針

- 内部状態は `dict[str, asyncio.Task]` **1つだけ**（新しい抽象を async 層に増やさない）。
- `track` は同キーの旧タスクを先に `cancel()` してから上書きする（重複投機の防止）。
- `add_done_callback` で必ず `untrack` し、例外は `logger.warning` に出すだけ（**再送出しない**）。
- `CancelledError` は握り潰す（`semantic_cache._handle_done` と同じ既存方針）。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

#: `cancel_prefix` のスコープ区切り。`"{book_id}_{ep}"` と `"{book_id}:{ep}"` の
#: 両方を実キーに使うため、ここでは区切り文字の境界でだけ部分一致させる
#: （`"7"` が `"70_1"` に誤爆しないため）。
_SCOPE_SEPARATORS = (":", "_", "/")


def _matches_scope(key: str, prefix: str) -> bool:
    """`key` が `prefix` と同じスコープに属するかを判定する。"""
    if not prefix:
        return False
    if key == prefix:
        return True
    return any(key.startswith(f"{prefix}{sep}") for sep in _SCOPE_SEPARATORS)


class PrefetchRegistry:
    """投機的プリフェッチのバックグラウンドタスク keyed レジストリ。

    公開 API は 4 つ（`track` / `cancel` / `cancel_prefix` / `stats`）のみ。
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancelled = 0
        self._failed = 0
        self._done = 0

    # ------------------------------------------------------------------
    # 登録・解除
    # ------------------------------------------------------------------
    def track(self, key: str, task: asyncio.Task) -> asyncio.Task:
        """`key` に `task` を登録する。同キーの旧タスクは先にキャンセルする。"""
        previous = self._tasks.get(key)
        if previous is not None and not previous.done():
            previous.cancel()
        self._tasks[key] = task
        task.add_done_callback(lambda t: self._on_done(key, t))
        return task

    def untrack(self, key: str) -> None:
        """`key` の登録を外す（タスク自体は止めない）。"""
        self._tasks.pop(key, None)

    def _on_done(self, key: str, task: asyncio.Task) -> None:
        """完了コールバック。必ず untrack し、統計だけ更新する。"""
        if self._tasks.get(key) is task:
            self._tasks.pop(key, None)
        if task.cancelled():
            self._cancelled += 1
            return
        exc = task.exception()
        if exc is not None:
            self._failed += 1
            logger.warning("[PREFETCH] task %s failed: %s", key, exc)
        else:
            self._done += 1

    # ------------------------------------------------------------------
    # 取り消し
    # ------------------------------------------------------------------
    async def cancel(self, key: str) -> int:
        """`key` のタスクを1本取り消す。実際に取り消した本数を返す。"""
        task = self._tasks.pop(key, None)
        if task is None:
            return 0
        if task.done():
            return 0
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return 1

    async def cancel_prefix(self, prefix: str) -> int:
        """`prefix` スコープに属するタスクをまとめて取り消す。本数を返す。"""
        if not prefix:
            return 0
        keys = [k for k in list(self._tasks) if _matches_scope(k, prefix)]
        if not keys:
            return 0
        cancelled: list[asyncio.Task] = []
        for k in keys:
            task = self._tasks.pop(k, None)
            if task is None or task.done():
                continue
            task.cancel()
            cancelled.append(task)
        if cancelled:
            await asyncio.gather(*cancelled, return_exceptions=True)
        return len(cancelled)

    # ------------------------------------------------------------------
    # 観測
    # ------------------------------------------------------------------
    def stats(self) -> dict[str, int]:
        """現在追跡中の本数と、累積の終了内訳を返す。"""
        return {
            "tracked": len(self._tasks),
            "cancelled": self._cancelled,
            "failed": self._failed,
            "done": self._done,
        }
