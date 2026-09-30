"""
是正手段の三段階トリアージ判定器（W4 Step 7）。

`AuditAgent.try_local_patch` は「パッチできるか」を試すだけで、
「どの手段で直すか」を決めていなかった（SafeReplacer → 追記 → LocalPolisher の3段のみ）。
ここでは LLM を1行も呼ばずに、

1. ``rule``  : 静的ルール置換で即時解決（LLM不要・最安価）
2. ``span``  : 1〜2段落の局所LLMパッチ（全文再生成を回避）
3. ``scene`` : シーン単位の再生成（既存経路に委ねる）
4. ``none``  : 自動で触らない（人手 / 既存経路をそのまま使う）

のどちらを使うかを決定する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.audit.static_rules import SEVERITY_CRITICAL, Issue
from src.audit.triage import (
    TRIAGE_MAJOR,
    TRIAGE_MINOR,
    classify_audit_outcomes,
    classify_static_issues,
)
from src.services.audit.targeted_diagnostic import TargetedDiagnostic

LEVEL_RULE = "rule"    # 決定的ルール置換
LEVEL_SPAN = "span"    # 段落単位の局所LLMパッチ
LEVEL_SCENE = "scene"  # シーン単位の再生成
LEVEL_NONE = "none"    # 自動で触らない

# 即時ルール置換で解決できる指摘のみ（この comboだけ rule へ上げる）
_RULE_LEVEL_TYPES = frozenset({"line_start_forbidden_punct", "title_length_exceeded"})


@dataclass(frozen=True)
class RepairPlan:
    """是正手段の決定結果（``reason`` はプロンプトではなくログ用）。"""

    level: str
    targets: tuple[int, ...]
    reason: str


def plan_repair(text: str, failed_outcomes: List[dict], static_issues: List[Issue]) -> RepairPlan:
    """是正手段を決める（純関数。LLMを1行も呼ばない）。

    判定順（この順で必ず評価する）:

    1. 静的 Issues に ``critical`` が1つでもあれば ``none``（人手。自動で触らない）
    2. 静的 Issues が全て即時ルールで解決できる型なら ``rule``
    3. ``classify_audit_outcomes`` が major なら ``scene``
    4. それ以外は ``span``（対象段落は TargetedDiagnostic に決めさせる）
    5. 対象段落が空なら ``none``（既存経路に委ねる）
    """
    issues = list(static_issues or [])
    outcomes = list(failed_outcomes or [])

    # 1. critical は自動で触らない
    if any(getattr(i, "severity", None) == SEVERITY_CRITICAL for i in issues):
        return RepairPlan(LEVEL_NONE, (), "静的ルールに critical があるため人手対応")

    # 2. 即時ルール置換で解決できる指摘のみ
    if (
        issues
        and classify_static_issues(issues) == TRIAGE_MINOR
        and all(getattr(i, "type", "") in _RULE_LEVEL_TYPES for i in issues)
    ):
        return RepairPlan(LEVEL_RULE, (), "即時ルール置換で解決可能な指摘のみ")

    # 3. オーディターが重大（エラー / critical）ならシーン再生成
    if classify_audit_outcomes(outcomes) == TRIAGE_MAJOR:
        return RepairPlan(LEVEL_SCENE, (), "オーディター判定が major のためシーン再生成")

    # 失敗が無ければ何も直さない
    if not outcomes:
        return RepairPlan(LEVEL_NONE, (), "是正対象の失敗なし")

    # 4. それ以外は段落単位の局所パッチ
    targets = tuple(
        t.index for t in TargetedDiagnostic().identify_weak_paragraphs(outcomes, text=text)
    )
    # 5. 対象段落が特定できなければ既存経路に委ねる
    if not targets:
        return RepairPlan(LEVEL_NONE, (), "対象段落を特定できなかったため既存経路へ委ねる")
    return RepairPlan(LEVEL_SPAN, targets, "段落単位の局所パッチで是正")
