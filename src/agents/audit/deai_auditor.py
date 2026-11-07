"""DeAIAuditor — AI感除去監査エージェント。

src/agents/audit.py から機能分割（案A+B）により新設。
旧パス ``src/agents/audit.py`` は shim として残す。
"""

from __future__ import annotations

from typing import Any

from src.backend.sharp_edge_preserver import check_edges_preserved
from src.llm.service import LLMService
from src.models.sharp_edge import SharpEdgeSpec


class DeAIAuditor:
    """AI感除去監査エージェント"""

    def __init__(
        self,
        repo=None,
        llm: LLMService = None,
        prompt_manager: Any = None,
        edge_preserver=None,
        *args,
        **kwargs,
    ):
        self.repo = repo
        self.llm = llm
        self.prompt_manager = prompt_manager
        self.edge_preserver = edge_preserver  # New parameter for semantic edge preservation

    async def audit(
        self,
        content: str,
        before_content: str | None = None,
        edges: list[SharpEdgeSpec] | None = None,
        emotional_hook: Any | None = None,
    ) -> tuple[bool, str]:
        if edges:
            if self.edge_preserver is not None:
                # Semantic mode: use SemanticEdgePreserver for robust detection
                semantic_lost, _ = await self.edge_preserver.check_edges_preserved(
                    before_content or "",
                    content,
                    edges,
                )
                lost = semantic_lost
            else:
                # Legacy string-only mode (backward compatible)
                lost = check_edges_preserved(
                    before_content or "",
                    content,
                    edges,
                )
            if lost:
                lost_types = ", ".join(e.edge_type for e in lost)
                return False, f"以下の角が削られました: {lost_types}"

        if emotional_hook is not None:
            hook_edges = [
                SharpEdgeSpec(
                    edge_type="emotional_hook",
                    description=getattr(emotional_hook, "one_line_intent", str(emotional_hook)),
                )
            ]
            if self.edge_preserver is not None:
                semantic_lost, _ = await self.edge_preserver.check_edges_preserved(
                    before_content or "",
                    content,
                    hook_edges,
                )
                lost = semantic_lost
            else:
                lost = check_edges_preserved(
                    before_content or "",
                    content,
                    hook_edges,
                )
            if lost:
                return (
                    False,
                    f"刺さりが削られました: {getattr(emotional_hook, 'one_line_intent', '')}",
                )

        if self.prompt_manager is None:
            return True, "OK"
        prompt = self.prompt_manager.build_critic_feedback_prompt(
            issue_list=None, draft_content=content, blueprint=content
        )
        result = await self.llm.generate_json(purpose="audit", prompt=prompt)
        metadata = result.get("metadata", {})
        return metadata.get("is_valid", True), metadata.get("feedback", "OK")
