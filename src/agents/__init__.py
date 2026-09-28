"""agents パッケージの公開シンボル。

ここで re-export するエージェントは、内部で LLM SDK (google-genai / openai) や
検索基盤をトップレベルで import する。API サーバーは起動時にエージェント
インスタンスを 1 つも作らないため、eager import すると起動が 10 秒以上遅れる。

そこで公開シンボルは PEP 562 のモジュール ``__getattr__`` で遅延公開し、
``from src.agents import WritingAgent`` などの既存 API はそのまま維持する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

#: 公開名 -> (定義モジュール, 属性名)
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "BaseAgent": ("src.agents.base", "BaseAgent"),
    "LogicalAuditor": ("src.agents.audit", "LogicalAuditor"),
    "AuditAgent": ("src.agents.audit_agent", "AuditAgent"),
    "BibleAgent": ("src.agents.bible", "BibleAgent"),
    "ContextBuilderAgent": ("src.agents.context_builder_agent", "ContextBuilderAgent"),
    "EnrichmentAgent": ("src.agents.enrichment_agent", "EnrichmentAgent"),
    "MarketingAgent": ("src.agents.marketing", "MarketingAgent"),
    "AgentContext": ("src.agents.orchestrator", "AgentContext"),
    "AgentName": ("src.agents.orchestrator", "AgentName"),
    "AgentResult": ("src.agents.orchestrator", "AgentResult"),
    "Orchestrator": ("src.agents.orchestrator", "Orchestrator"),
    "AgentEvent": ("src.agents.event_bus", "AgentEvent"),
    "EventBus": ("src.agents.event_bus", "EventBus"),
    "PlanningAgent": ("src.agents.planning", "PlanningAgent"),
    "PlotAgent": ("src.agents.plot", "PlotAgent"),
    "WritingAgent": ("src.agents.writing", "WritingAgent"),
}

if TYPE_CHECKING:  # pragma: no cover - 型チェックのみ
    from src.agents.audit import LogicalAuditor
    from src.agents.audit_agent import AuditAgent
    from src.agents.base import BaseAgent
    from src.agents.bible import BibleAgent
    from src.agents.context_builder_agent import ContextBuilderAgent
    from src.agents.enrichment_agent import EnrichmentAgent
    from src.agents.event_bus import AgentEvent, EventBus
    from src.agents.marketing import MarketingAgent
    from src.agents.orchestrator import AgentContext, AgentName, AgentResult, Orchestrator
    from src.agents.planning import PlanningAgent
    from src.agents.plot import PlotAgent
    from src.agents.writing import WritingAgent


def __getattr__(name: str) -> Any:
    """公開シンボルを初回アクセス時に import する (PEP 562)。"""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module_path, attr = target
    value = getattr(importlib.import_module(module_path), attr)
    globals()[name] = value  # 2 回目以降は __getattr__ を経由しない
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    "BaseAgent",
    "LogicalAuditor",
    "AuditAgent",
    "BibleAgent",
    "ContextBuilderAgent",
    "EnrichmentAgent",
    "PlotAgent",
    "PlanningAgent",
    "WritingAgent",
    "MarketingAgent",
    "AgentName",
    "AgentContext",
    "AgentResult",
    "Orchestrator",
    "AgentEvent",
    "EventBus",
]
