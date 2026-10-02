"""
三段階トリアージ判定器（W4 Step 2）。

「1 オーディターでも落ちたらエピソード全文再執筆」を避けるため、
静的 Issues と LLM オーディターの outcome を
「即時ルール置換 → 局所スパン置換 → シーン再生成」の3段階へ正規化する純関数群。

LLM・ネットワーク・DB には一切依存しない（import しただけで安全）。
"""

from __future__ import annotations

from typing import Iterable, List

from src.audit.static_rules import SEVERITY_CRITICAL, Issue

# トリアージ段階（ RepairPlanner / AuditAgent が参照する）
TRIAGE_MINOR = "minor"    # LLM不要・即時ルールで解決
TRIAGE_MEDIUM = "medium"  # 1〜2段落の局所LLMパッチ
TRIAGE_MAJOR = "major"    # シーン単位の再生成

# outcome の severity 値 → トリアージ段階の対応表
_MAJOR_SEVERITIES = frozenset({"critical"})
_MEDIUM_SEVERITIES = frozenset({"high"})
# minor / medium / low および未知の値は minor に落とす（未知値で判定を壊さない）


def _as_list(items: Iterable[object] | None) -> List[object]:
    """None / 非シーケンスを安全に空リストへ倒す。"""
    if not items:
        return []
    try:
        return list(items)
    except TypeError:
        return []


def classify_static_issues(issues: List[Issue]) -> str:
    """静的Issuesを最も重いtriage levelへ集約する。

    - ``severity == "critical"`` が1つでもあれば :data:`TRIAGE_MAJOR`
    - そうでなく severity を持つもの（既定 minor）が1つでもあれば :data:`TRIAGE_MINOR`
    - Issues が空でも :data:`TRIAGE_MINOR`（= 打つ手なし＝既存経路に委ねる）
    """
    items = _as_list(issues)
    for issue in items:
        severity = getattr(issue, "severity", None)
        if severity and severity == SEVERITY_CRITICAL:
            return TRIAGE_MAJOR
    return TRIAGE_MINOR


def classify_audit_outcomes(outcomes: List[dict]) -> str:
    """AuditAgent の outcome dict 群をtriage levelへ集約する。

    - ``error`` 付き、または severity / effective_severity が ``critical`` → :data:`TRIAGE_MAJOR`
    - ``high`` → :data:`TRIAGE_MEDIUM`
    - ``medium`` / ``low`` / 未知の値 → :data:`TRIAGE_MINOR`
    """
    worst = TRIAGE_MINOR
    for outcome in _as_list(outcomes):
        if not isinstance(outcome, dict):
            continue
        if outcome.get("error"):
            return TRIAGE_MAJOR
        severity = outcome.get("effective_severity") or outcome.get("severity")
        if not isinstance(severity, str):
            continue
        normalized = severity.strip().lower()
        if normalized in _MAJOR_SEVERITIES:
            return TRIAGE_MAJOR
        if normalized in _MEDIUM_SEVERITIES:
            worst = TRIAGE_MEDIUM
    return worst
