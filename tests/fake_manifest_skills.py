"""from_manifest テスト用のダミースキルモジュール。"""

from __future__ import annotations

from typing import Any

from src.agents.orchestrator import AgentContext, AgentResult
from src.agents.skill_base import SkillAgent


class FirstSkill(SkillAgent):
    """常に成功して自分の名前を記録するスキル。"""

    def __init__(self, repo: Any = None, **kwargs: Any):
        super().__init__(repo=repo, **kwargs)

    async def execute(self, ctx: AgentContext) -> AgentResult:
        order = list(ctx.artifacts.get("order", []))
        order.append(self._skill_name)
        return AgentResult(next_agent=None, artifacts={"order": order})


class SecondSkill(FirstSkill):
    pass
