"""audit_agent パッケージ（監査エージェント機能分割）。

src/agents/audit_agent.py から機能分割（案A+B）により新設。
旧パス ``src/agents/audit_agent.py`` は shim として残す。
"""

from __future__ import annotations

from src.agents.audit_agent.config import (
    DEFAULT_ENABLE_AUDIT_ADVISORY_STRICT_GUARD,
    DEFAULT_ENABLE_AUDIT_LEGACY_CORE,
    DEFAULT_AUDIT_ADVISORY_THRESHOLD,
    DEFAULT_AUDIT_GATE_THRESHOLD,
    AUDIT_GATE_ADVISORY_SEVERITIES,
    AUDIT_GATE_CONFIDENCE_WEIGHT,
    AUDIT_GATE_DOWNGRADE,
    AUDIT_GATE_PASS_SCORE,
    AUDIT_GATE_PENALTY_SCORE,
    AUDIT_GATE_SEVERITY_WEIGHTS,
    get_advisory_threshold,
    get_gate_threshold,
    is_advisory_strict_guard_enabled,
    is_audit_legacy_core_enabled,
    is_async_polish_enabled,
    is_local_patch_enabled,
    is_repair_budget_enabled,
    is_score_gate_enabled,
    is_span_patch_enabled,
    is_unified_auditor_blocking,
)
from src.agents.audit_agent.criteria import (
    AUDIT_CRITERIA,
    CORE_AUDIT_CRITERIA,
    UNIFIED_AUDIT_CRITERION,
    AuditCriterion,
)
from src.agents.audit_agent.gate import evaluate_gate
from src.agents.audit_agent.agent import (
    AuditAgent,
    AuditSkillAgent,
)

__all__ = [
    "AuditAgent",
    "AuditSkillAgent",
    "AuditCriterion",
    "AUDIT_CRITERIA",
    "CORE_AUDIT_CRITERIA",
    "UNIFIED_AUDIT_CRITERION",
    "evaluate_gate",
    "DEFAULT_ENABLE_AUDIT_ADVISORY_STRICT_GUARD",
    "DEFAULT_ENABLE_AUDIT_LEGACY_CORE",
    "DEFAULT_AUDIT_ADVISORY_THRESHOLD",
    "DEFAULT_AUDIT_GATE_THRESHOLD",
    "AUDIT_GATE_ADVISORY_SEVERITIES",
    "AUDIT_GATE_CONFIDENCE_WEIGHT",
    "AUDIT_GATE_DOWNGRADE",
    "AUDIT_GATE_PASS_SCORE",
    "AUDIT_GATE_PENALTY_SCORE",
    "AUDIT_GATE_SEVERITY_WEIGHTS",
    "get_advisory_threshold",
    "get_gate_threshold",
    "is_advisory_strict_guard_enabled",
    "is_audit_legacy_core_enabled",
    "is_async_polish_enabled",
    "is_local_patch_enabled",
    "is_repair_budget_enabled",
    "is_score_gate_enabled",
    "is_span_patch_enabled",
    "is_unified_auditor_blocking",
]
