"""ドメイン層のポート定義パッケージ。

アプリケーション層・インフラ層に依存せず、ドメイン層が必要とする
外部依存の抽象（ポート）をここに定義する。これにより、ドメイン層は
旧レイアウト（src.agents / src.services / src.backend）に直接依存せず、
ポート経由の DI で疎結合に保たれる。
"""

from __future__ import annotations

from src.domain.ports.auditor import IAuditor
from src.domain.ports.pdca_runner import IPDCARunner

__all__ = ["IAuditor", "IPDCARunner"]
