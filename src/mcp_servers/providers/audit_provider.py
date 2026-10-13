"""Compliance and Audit Provider for MCP Server."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class AuditRule:
    """監査ルール定義"""
    rule_id: str
    description: str
    severity: str = "warning"  # error, warning, info


@dataclass
class AuditRequest:
    """監査リクエスト"""
    text: str
    active_rules: List[str] = field(default_factory=list)


@dataclass
class AuditViolation:
    """違反事項"""
    rule_id: str
    message: str
    severity: str


@dataclass
class AuditResponse:
    """監査レスポンス"""
    is_compliant: bool
    violations: List[AuditViolation] = field(default_factory=list)
    score: float = 100.0


class AuditProvider:
    """小説やシーンの品質・コンプライアンス監査を行うプロバイダー"""

    def __init__(self) -> None:
        self.rules: Dict[str, AuditRule] = {}

    def register_rule(self, rule: AuditRule) -> None:
        """監査ルールを登録する"""
        self.rules[rule.rule_id] = rule

    def audit(self, request: AuditRequest) -> AuditResponse:
        """テキストに対してルール監査を実行する"""
        violations: List[AuditViolation] = []
        text = request.text

        # 簡易的なチェックルール適用
        for rule_id, rule in self.rules.items():
            if request.active_rules and rule_id not in request.active_rules:
                continue

            # ルールごとのテストロジック（例: 禁止ワードや文字数、常体・敬体など）
            if rule_id == "no_forbidden_words" and "NGWORD" in text:
                violations.append(
                    AuditViolation(
                        rule_id=rule_id,
                        message="Forbidden word 'NGWORD' detected.",
                        severity=rule.severity,
                    )
                )
            elif rule_id == "min_length" and len(text) < 10:
                violations.append(
                    AuditViolation(
                        rule_id=rule_id,
                        message="Text is too short (less than 10 chars).",
                        severity=rule.severity,
                    )
                )

        is_compliant = len([v for v in violations if v.severity == "error"]) == 0
        score = max(0.0, 100.0 - len(violations) * 20.0)

        return AuditResponse(
            is_compliant=is_compliant,
            violations=violations,
            score=score,
        )
