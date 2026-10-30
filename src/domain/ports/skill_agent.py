"""スキルエージェントアプリケーションポート（ドメイン層定義）。

WritingAgent / ContextBuilderAgent / IllustrationAgent などの
``src.agents.*`` エージェントが共通に持つ ``execute(ctx)`` メソッドを
抽象化したポート。ドメイン層はこのポート経由でエージェントを利用し、
旧レイアウトに直接依存しない。

実装はアプリケーション/インフラ層が注入する。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ISkillAgent(Protocol):
    """エージェントの実行エントリポイント。

    ``ctx`` は辞書ライクなオブジェクト（`book_id`, `ep_num`, `artifacts` 等を
    持つ）を受け取り、実行結果（`error`, `draft_text`, `artifacts` 等を持つ）
    を返すことが期待される。
    """

    async def execute(self, ctx: Any) -> Any:
        ...
