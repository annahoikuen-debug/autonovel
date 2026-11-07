"""audit_agent 監査判定項目の定義。

src/agents/audit_agent.py から機能分割（案A+B）により新設。
旧パス ``src/agents/audit_agent.py`` は shim として残す。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditCriterion:
    """監査1件を表す不変レコード。

    ``audit_id`` はイベント追跡用の安定 ID（Step 21）。
    ``severity`` は「不合格했을 때の重篤さ」で、ゲート集約の重み付けに使う。
    ``learning_key`` は ``_check_learning_adjustment`` に渡す学習データキー。
    ``blocking`` は False のときゲート判定の集計対象から外れる
    （UnifiedAuditor は LLM 未設定時に fail-closed するため、
    本番未設定時に意図せず全話不合格にしないよう既定 False とする）。
    """

    audit_id: str
    label: str
    severity: str
    learning_key: str
    blocking: bool = True


#: 既存5監査（変更禁止）。UnifiedAuditor 統合は本リストを変更せず追加で行う。
CORE_AUDIT_CRITERIA: tuple[AuditCriterion, ...] = (
    AuditCriterion(
        audit_id="fast_screen",
        label="プロット高速スクリーニング",
        severity="high",
        learning_key="fast_screen",
    ),
    AuditCriterion(
        audit_id="logical_consistency",
        label="論理整合性監査",
        severity="high",
        learning_key="logical_consistency",
    ),
    AuditCriterion(
        audit_id="deai",
        label="AI感除去監査（DeAI）",
        severity="medium",
        learning_key="deai",
    ),
    AuditCriterion(
        audit_id="ability_consistency",
        label="能力整合性チェック",
        severity="medium",
        learning_key="ability_consistency",
    ),
    AuditCriterion(
        audit_id="causal_integrity",
        label="プロット整合性モニター（因果律）",
        severity="high",
        learning_key="causal_integrity",
    ),
)

#: UnifiedAuditor（定性的判断フェーズ, v6-A2）。既存5監査とは独立した第6の観点で、
#: 既存判定項目を置き換えずに「追加」する。
UNIFIED_AUDIT_CRITERION = AuditCriterion(
    audit_id="unified_qualitative",
    label="定性的判断（UnifiedAuditor 統合）",
    severity="medium",
    learning_key="unified_qualitative",
    blocking=False,
)

AUDIT_CRITERIA: tuple[AuditCriterion, ...] = CORE_AUDIT_CRITERIA + (UNIFIED_AUDIT_CRITERION,)
