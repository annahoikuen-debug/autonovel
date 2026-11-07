"""InternalLogicValidator — 内部ロジック検証エージェント。

src/agents/audit.py から機能分割（案A+B）により新設。
旧パス ``src/agents/audit.py`` は shim として残す。
"""

from __future__ import annotations

from typing import Any


class InternalLogicValidator:
    """内部ロジック(アリバイ・タイムライン・情報非対称)の整合性検証エージェント。

    テスト・簡易利用側は PromptManager と generate_json 呼び出しを
     kwargs 経由で注入できる（LogicalAuditor と同様の設計）。
    """

    def __init__(
        self, repo: Any = None, llm: Any = None, ctx_mgr: Any = None, pm: Any = None, **kwargs
    ):
        self.repo = repo
        self.ctx_mgr = ctx_mgr
        self.prompt_manager = pm

        # Priority 1: Explicit generate_json provided in kwargs (Common in tests)
        if "generate_json" in kwargs:
            self.llm = kwargs["generate_json"]
        # Priority 2: llm argument provided
        elif llm is not None:
            self.llm = llm
        else:
            self.llm = None

        self.wave_analyzer = None

    async def validate_alibi_and_timeline(
        self, blueprint: str, script: str
    ) -> tuple[bool, list[str]]:
        """アリバイとタイムラインの整合性を検証する（スタブ）。"""
        return True, []

    async def check_information_asymmetry(
        self, past_info: str, current_info: str
    ) -> tuple[bool, list[str]]:
        """情報の非対称性を検証する（スタブ）。"""
        return True, []
