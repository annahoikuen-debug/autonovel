"""src/agents/audit_agent — 後方互換 shim。

実装は ``src/agents/audit_agent/`` パッケージ（audit_agent/agent.py 等）に移設済み。
このモジュールは旧 import 経路（``from src.agents.audit_agent import ...``）を
維持するためにパッケージから再エクスポートする。

分割は案A+B（ファイル隔離＋旧パスshim＋関連テスト全緑）に従う。
削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。
"""

from __future__ import annotations

import warnings

warnings.warn(
    "src.agents.audit_agent is deprecated; use src.agents.audit_agent package instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.agents.audit_agent import (  # noqa: F401, F403
    AuditAgent,
    AuditSkillAgent,
    AuditCriterion,
    AUDIT_CRITERIA,
    CORE_AUDIT_CRITERIA,
    UNIFIED_AUDIT_CRITERION,
    evaluate_gate,
    DEFAULT_ENABLE_AUDIT_ADVISORY_STRICT_GUARD,
    DEFAULT_ENABLE_AUDIT_LEGACY_CORE,
    DEFAULT_ENABLE_AUDIT_SPAN_PATCH,
    DEFAULT_ENABLE_AUDIT_REPAIR_BUDGET,
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

__all__ = [name for name in dir() if not name.startswith("_")]
