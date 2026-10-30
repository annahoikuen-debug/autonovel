"""オーディターアプリケーションポート（ドメイン層定義）。

WritingCoordinator などのドメイン層が、旧レイアウトの
``src.agents.specialists.UnifiedAuditor`` に直接依存せず、本ポート経由で
定量監査を利用するためのインターフェース。

実装はアプリケーション/インフラ層が注入する（ドメイン層は実装を知らない）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IAuditor(ABC):
    """テキストの定量監査を行うポート。"""

    @abstractmethod
    def audit_quantitative(self, text: str) -> tuple[float, dict[str, Any]]:
        """テキストを監査し、(スコア, メタ辞書) を返す。

        戻り値のメタ辞書は ``UnifiedAuditor.audit_quantitative`` と互換の
        キー（``cliches``, ``dialogue_ratio``, ``rhythm_score`` 等）を持つ
        ことが期待される。
        """
        ...
