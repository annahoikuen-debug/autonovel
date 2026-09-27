"""ドメイン層のポート定義。

ドメイン層はインフラストラクチャ (src.infrastructure / src.backend) に
依存してはならない。本モジュール群はその境界を表す。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IMetricsRecorder(Protocol):
    """メトリクス記録のポート。

    ドメイン層は Prometheus 等の実装に依存せず、このポートに依存する。
    実装はインフラ層が注入する。未注入時は no-op を使う。
    """

    def record_book_score(self, book_id: Any, score: Any) -> None:
        """書籍スコアの記録。失敗しても呼び出し元の処理は中断させない。"""
        ...


class NoOpMetricsRecorder:
    """メトリクス未設定時に使用する no-op 実装。"""

    def record_book_score(self, book_id: Any, score: Any) -> None:
        return None


#: デフォルトのメトリクスレコーダ (何もしない)。
NOOP_METRICS_RECORDER = NoOpMetricsRecorder()


__all__ = [
    "IMetricsRecorder",
    "NoOpMetricsRecorder",
    "NOOP_METRICS_RECORDER",
]
