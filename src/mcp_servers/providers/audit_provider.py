"""Compliance and Audit Provider for MCP Server."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class AuditRule:
    """監査ルール定義"""
    rule_id: str
    description: str
    severity: str = "warning"  # error, warning, info
    validator: Optional[Callable[[str, Any], List[str]]] = None


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
    line_number: Optional[int] = None
    snippet: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass
class AuditResponse:
    """監査レスポンス"""
    is_compliant: bool
    violations: List[AuditViolation] = field(default_factory=list)
    score: float = 100.0


@dataclass
class DeterministicScreenResult:
    """決定論的プレ・オーディット結果（LLMコール削減用）"""
    passed: bool
    score: float
    violations: List[AuditViolation]
    bypass_eligible: bool  # TrueならLLMオーディターの呼び出しを安全にスキップ可能
    details: Dict[str, Any] = field(default_factory=dict)


class AuditProvider:
    """小説やシーンの品質・コンプライアンス監査を行う決定論的ルールプロバイダー"""

    # 代表的なAI定型句・クリシェ
    DEFAULT_AI_CLICHES = (
        r"と言えるだろう",
        r"に他ならなかった",
        r"筆舌に尽くしがたい",
        r"言わずもがな",
        r"息を呑むような",
        r"言葉を失った",
    )

    def __init__(self) -> None:
        self.rules: Dict[str, AuditRule] = {}
        self.forbidden_words: List[str] = ["NGWORD"]
        self._init_default_rules()

    def _init_default_rules(self) -> None:
        """決定論的な小説作法・品質検査デフォルトルールの登録"""
        self.register_rule(
            AuditRule(
                rule_id="no_forbidden_words",
                description="禁止ワードや不適切語句の検出",
                severity="error",
            )
        )
        self.register_rule(
            AuditRule(
                rule_id="unclosed_quotes",
                description="会話文括弧（「」『』（）等）の閉じ忘れチェック",
                severity="error",
            )
        )
        self.register_rule(
            AuditRule(
                rule_id="odd_ellipses_or_dashes",
                description="三点リーダー（……）やダッシュ（――）が奇数個の検出",
                severity="warning",
            )
        )
        self.register_rule(
            AuditRule(
                rule_id="dialogue_trailing_period",
                description="会話文末尾の余計な句点（「〜。」）の検出",
                severity="warning",
            )
        )
        self.register_rule(
            AuditRule(
                rule_id="excessive_consecutive_blank_lines",
                description="3行以上連続する空行の検出",
                severity="warning",
            )
        )
        self.register_rule(
            AuditRule(
                rule_id="min_length",
                description="最低文字数（10文字未満）の逸脱検出",
                severity="error",
            )
        )
        self.register_rule(
            AuditRule(
                rule_id="ai_cliche_density",
                description="AI定型表現・フィラーの過剰集中検出",
                severity="info",
            )
        )

    def register_rule(self, rule: AuditRule) -> None:
        """監査ルールを登録する"""
        self.rules[rule.rule_id] = rule

    def set_forbidden_words(self, words: List[str]) -> None:
        """禁止語句リストを更新する"""
        self.forbidden_words = list(words)

    def pre_screen(
        self,
        text: str,
        specialist_name: Optional[str] = None,
        bypass_threshold: float = 90.0,
    ) -> DeterministicScreenResult:
        """決定論的プレ・オーディットを実行し、LLMオーディター呼び出しのスキップ可否を判定する"""
        req = AuditRequest(text=text)
        res = self.audit(req)

        error_count = sum(1 for v in res.violations if v.severity == "error")
        warning_count = sum(1 for v in res.violations if v.severity == "warning")

        # 重大なエラーがなく、スコアが閾値以上であればLLMを呼ばずにパス可能
        bypass_eligible = (error_count == 0) and (res.score >= bypass_threshold)

        # 特定スペシャリスト（例: style や formatting）向けには、作法違反が多すぎる場合は
        # LLMを呼ぶまでもなく即座に不合格としてリファインへ回す判定も可能
        passed = (error_count == 0) and (res.score >= 60.0)

        return DeterministicScreenResult(
            passed=passed,
            score=res.score,
            violations=res.violations,
            bypass_eligible=bypass_eligible,
            details={
                "specialist_name": specialist_name,
                "error_count": error_count,
                "warning_count": warning_count,
                "total_violations": len(res.violations),
                "text_length": len(text),
            },
        )

    def audit(self, request: AuditRequest) -> AuditResponse:
        """テキストに対して決定論的ルール監査を実行する"""
        violations: List[AuditViolation] = []
        text = request.text
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        active = set(request.active_rules) if request.active_rules else set(self.rules.keys())

        # 1. no_forbidden_words
        if "no_forbidden_words" in active:
            for word in self.forbidden_words:
                if word in text:
                    for i, line in enumerate(lines, 1):
                        if word in line:
                            violations.append(
                                AuditViolation(
                                    rule_id="no_forbidden_words",
                                    message=f"Forbidden word '{word}' detected.",
                                    severity=self.rules["no_forbidden_words"].severity,
                                    line_number=i,
                                    snippet=line.strip()[:60],
                                    suggestion=f"'{word}' を別の表現に置換してください。",
                                )
                            )

        # 2. min_length
        if "min_length" in active and len(text.strip()) < 10:
            violations.append(
                AuditViolation(
                    rule_id="min_length",
                    message="Text is too short (less than 10 chars).",
                    severity=self.rules["min_length"].severity,
                    suggestion="本文の最小文字数を満たしてください。",
                )
            )

        # 3. unclosed_quotes
        if "unclosed_quotes" in active:
            quote_pairs = [("「", "」"), ("『", "』"), ("（", "）"), ("【", "】")]
            for opener, closer in quote_pairs:
                open_cnt = text.count(opener)
                close_cnt = text.count(closer)
                if open_cnt != close_cnt:
                    violations.append(
                        AuditViolation(
                            rule_id="unclosed_quotes",
                            message=f"括弧 '{opener}{closer}' の対応が不一致です（開き: {open_cnt}, 閉じ: {close_cnt}）。",
                            severity=self.rules["unclosed_quotes"].severity,
                            suggestion="閉じ忘れまたは余分な開き括弧を修正してください。",
                        )
                    )

        # 4. odd_ellipses_or_dashes
        if "odd_ellipses_or_dashes" in active:
            for match in re.finditer(r"…+|―+|―+", text):
                chunk = match.group(0)
                if len(chunk) % 2 != 0:
                    line_no = text[:match.start()].count("\n") + 1
                    violations.append(
                        AuditViolation(
                            rule_id="odd_ellipses_or_dashes",
                            message=f"三点リーダーまたはダッシュが奇数個（{len(chunk)}個）使用されています。",
                            severity=self.rules["odd_ellipses_or_dashes"].severity,
                            line_number=line_no,
                            snippet=chunk,
                            suggestion="作法に合わせ2個セット（偶数個）に統一してください。",
                        )
                    )

        # 5. dialogue_trailing_period
        if "dialogue_trailing_period" in active:
            dialogue_period_pattern = re.compile(r"「[^」\n]*?[。]」")
            for i, line in enumerate(lines, 1):
                for match in dialogue_period_pattern.finditer(line):
                    violations.append(
                        AuditViolation(
                            rule_id="dialogue_trailing_period",
                            message=f"会話文の末尾に句点が付いています: {match.group(0)}",
                            severity=self.rules["dialogue_trailing_period"].severity,
                            line_number=i,
                            snippet=match.group(0),
                            suggestion="会話文末尾の『。』を除去してください。",
                        )
                    )

        # 6. excessive_consecutive_blank_lines
        if "excessive_consecutive_blank_lines" in active:
            consecutive_blanks = 0
            for i, line in enumerate(lines, 1):
                if not line.strip():
                    consecutive_blanks += 1
                    if consecutive_blanks >= 3:
                        violations.append(
                            AuditViolation(
                                rule_id="excessive_consecutive_blank_lines",
                                message="空行が3行以上連続しています。",
                                severity=self.rules["excessive_consecutive_blank_lines"].severity,
                                line_number=i,
                                suggestion="空行は1〜2行に抑えてください。",
                            )
                        )
                        consecutive_blanks = 0
                else:
                    consecutive_blanks = 0

        # 7. ai_cliche_density
        if "ai_cliche_density" in active:
            cliche_hits = 0
            for pattern in self.DEFAULT_AI_CLICHES:
                cliche_hits += len(re.findall(pattern, text))
            if cliche_hits >= 4:
                violations.append(
                    AuditViolation(
                        rule_id="ai_cliche_density",
                        message=f"AI定型構文・クリシェが多発しています（検出数: {cliche_hits}箇所）。",
                        severity=self.rules["ai_cliche_density"].severity,
                        suggestion="人間味のある自然な描写・比喩に言い換えてください。",
                    )
                )

        # スコア計算: error=15点減点, warning=5点減点, info=2点減点
        penalty = 0.0
        for v in violations:
            if v.severity == "error":
                penalty += 15.0
            elif v.severity == "warning":
                penalty += 5.0
            else:
                penalty += 2.0

        score = max(0.0, round(100.0 - penalty, 1))
        is_compliant = not any(v.severity == "error" for v in violations)

        return AuditResponse(
            is_compliant=is_compliant,
            violations=violations,
            score=score,
        )

