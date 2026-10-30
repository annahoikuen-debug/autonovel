"""Unit of Work application port.

`BookUseCases` などのアプリケーション層ユースケースが、旧レイアウトの
`src.backend.database.uow.UnitOfWork` に直接依存せず、
本ポート経由でトランザクション管理を利用するためのインターフェース。

実装はインフラ層（`src.backend` 等）が注入する。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IUnitOfWork(Protocol):
    """Unit of Work のポート。"""

    @property
    def session(self) -> Any:
        """DB セッション。"""
        ...

    async def commit(self) -> None:
        """現在のトランザクションをコミットする。"""
        ...

    async def rollback(self) -> None:
        """現在のトランザクションをロールバックする。"""
        ...

    async def close(self) -> None:
        """リソースを解放する。"""
        ...
