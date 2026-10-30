"""PDCA runner アプリケーションポート（ドメイン層定義）。

WritingCoordinator などのドメイン層が、旧レイアウトの
``src.services.pdca_cycle.ClosedLoopPDCARunner`` や
``src.services.audit_aggregator.AuditAggregator`` に直接依存せず、
本ポート経由で PDCA 閉ループ再執筆を利用するためのインターフェース。

実装はアプリケーション/インフラ層が注入する（ドメイン層は実装を知らない）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IPDCARunner(ABC):
    """PDCA 閉ループ再執筆を行うポート。"""

    @abstractmethod
    async def run_pdca_cycle(
        self,
        initial_context: dict[str, Any],
        genre: str = "general",
        phase: str = "draft",
    ) -> tuple[str, Any]:
        """PDCA サイクルを実行し、(下書き本文, 結果) を返す。

        ``initial_context`` には少なくとも ``book_id``, ``ep_num``,
        ``low_dimensions``, ``regeneration_actions`` を含むことが期待される。
        """
        ...
