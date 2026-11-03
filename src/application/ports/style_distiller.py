"""文体蒸留サービスの port（interfaces / 配線側が具象を注入する）。

実体 ``StyleDistillerService`` は旧レイヤー ``src.services.style_distiller``
に残しており、構造的型付け（Protocol）でここに適合する。
"""

from __future__ import annotations

from typing import Protocol

from src.models.style_profile import StyleProfile


class IStyleDistiller(Protocol):
    """サンプルテキストから作家性 DNA（StyleProfile）を抽出するサービスの契約。"""

    async def distill_from_text(self, sample_text: str, name_hint: str | None = None) -> StyleProfile:
        """サンプルテキストから StyleProfile を抽出する。"""
        ...
