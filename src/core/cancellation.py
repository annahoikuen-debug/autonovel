"""協力的キャンセルトークン（PLAN_W6 Step 2）。

`asyncio.Task.cancel()` は「次の await ポイントで強制停止」しかできない。
バッチ処理の途中（Embedding 呼び出しを N 回回すようなループ）では、
協調的にしか止められないので **協力的キャンセルトークン** が必要になる。

実測事実: `grep -rn "asyncio.Event" src/` → **0 ヒット**。
つまりリポジトリには此类のトークンが存在せず、本ファイルが最初の1つになる。

設計方針（PLAN_W6 §0.1）:
- `asyncio` と `typing` のみを import する（新しい抽象を async 層に増やさない）。
- `contextvars` には入れない（jj 伝播は別ステップのスコープ）。
- `__aenter__` / `__aexit__` は実装しない（API を増やさない）。
"""

from __future__ import annotations

import asyncio


class CancellationToken:
    """「キャンセルされるまで待つ」だけの薄いトークン。

    Args:
        name: ログ出力用の識別名（省略可）。
    """

    def __init__(self, name: str = "") -> None:
        self._name = name
        self._event = asyncio.Event()

    @property
    def name(self) -> str:
        return self._name

    def cancel(self) -> None:
        """キャンセルを通知する。

        `asyncio.Event` はスレッドセーフではないため、別スレッドから呼ばれても
        落ち 않도록 `RuntimeError` は握り潰す。
        """
        try:
            self._event.set()
        except RuntimeError:  # pragma: no cover - 防御的（イベントループ未実行時）
            pass

    def is_cancelled(self) -> bool:
        """キャンセル済みなら True。"""
        return self._event.is_set()

    async def wait(self) -> None:
        """キャンセルされるまで待つ。"""
        await self._event.wait()

    def raise_if_cancelled(self) -> None:
        """キャンセル済みなら `asyncio.CancelledError` を送出する。"""
        if self._event.is_set():
            raise asyncio.CancelledError(self._name or "cancelled")

    @property
    def cancelled_event(self) -> asyncio.Event:
        """`asyncio.wait_for` 等へそのまま渡せる内部イベント。"""
        return self._event
