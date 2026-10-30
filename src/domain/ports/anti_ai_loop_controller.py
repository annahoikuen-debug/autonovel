"""Anti-AI ループコントローラーアプリケーションポート（ドメイン層定義）。

``src.services.anti_ai.loop_controller.AntiAILoopController`` を抽象化したポート。
ドメイン層はこのポート経由で Anti-AI 修正ループを利用し、旧レイアウトに
直接依存しない。

実装はアプリケーション/インフラ層が注入する。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IAntiAILoopController(Protocol):
    """生成テキストの Anti-AI 修正ループを実行するポート。"""

    async def run(self, text: str) -> Any:
        """テキストを修正し、結果オブジェクトを返す。

        戻り値は少なくとも ``text``, ``final_score``, ``iterations``,
        ``to_dict()`` を持つことが期待される。
        """
        ...
