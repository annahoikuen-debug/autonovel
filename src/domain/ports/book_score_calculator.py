"""ブックスコア計算アプリケーションポート（ドメイン層定義）。

``src.services.book_score_service.BookScoreCalculator`` を抽象化したポート。
ドメイン層はこのポート経由で BookScore を計算し、旧レイアウトに直接
依存しない。

実装はアプリケーション/インフラ層が注入する。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IBookScoreCalculator(Protocol):
    """チャプターの BookScore を計算するポート。"""

    async def calculate(
        self,
        book_id: int,
        chapter_number: int,
        ctx: Any,
        genre: str = "",
        phase: str = "",
    ) -> Any:
        ...
