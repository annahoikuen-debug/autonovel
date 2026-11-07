"""audit_agent ゲート集約ロジック。

src/agents/audit_agent.py から機能分割（案A+B）により新設。
旧パス ``src/agents/audit_agent.py`` は shim として残す。
"""

from __future__ import annotations

from typing import Any

from src.agents.audit_agent.config import (
    AUDIT_GATE_ADVISORY_SEVERITIES,
    AUDIT_GATE_PASS_SCORE,
    DEFAULT_AUDIT_ADVISORY_THRESHOLD,
    DEFAULT_AUDIT_GATE_THRESHOLD,
    get_advisory_threshold,
    get_gate_threshold,
    is_advisory_strict_guard_enabled,
    is_score_gate_enabled,
)


def evaluate_gate(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """5監査を 0-100 に正規化し、severity 重み＋学習調整で集約する（モジュールヘルパ）。

    Args:
        outcomes: ``run_audit_phase`` が返す outcome 辞書の一覧

    Returns:
        ``mode`` / ``aggregate_score`` / ``threshold`` / ``requires_regeneration``
        / ``critical_failure`` / ``scored_audit_ids`` を含む辞書。
    """
    threshold = get_gate_threshold()
    blocking = [o for o in outcomes if o["blocking"]]
    scored = blocking or outcomes

    weighted_sum = sum(o["score"] * o["weight"] for o in scored)
    weight_total = sum(o["weight"] for o in scored)
    aggregate = (weighted_sum / weight_total) if weight_total else AUDIT_GATE_PASS_SCORE

    critical_failure = any(o["effective_severity"] == "critical" for o in scored)
    failed = [o for o in outcomes if not o["passed"]]

    if is_score_gate_enabled():
        requires_regeneration = bool(failed) and (aggregate < threshold or critical_failure)
        mode = "score_aggregation"
    else:
        # ロールバック: 従来の全滅式ゲート
        requires_regeneration = bool(failed)
        mode = "all_or_nothing"

    # W4 Step 9: Advisory（警告通過）帯。
    # 「不合格だが致命でもない」= failed の effective_severity がすべて
    # AUDIT_GATE_ADVISORY_SEVERITIES に含まれ、かつ総合スコアが
    # advisory_threshold 以上のときだけ再執筆を警告通過へ落とす。
    #
    # 帯は ``advisory_threshold < threshold`` のときだけ有効（= aggregate が
    # [advisory_threshold, threshold) に落ちる場合だけ relief する）。これにより
    # 意図的に上げた ``AUDIT_GATE_THRESHOLD``（= 手動の厳格化）が
    # advisory に上書きされて取り消される事故を防ぐ。
    #
    # W4 Step 11 実バグB: 上記ガードだけでは ``AUDIT_GATE_THRESHOLD`` を
    # 手動で上げた場合（例: 99.0）既定 advisory（80.0）との大小関係
    # ``80 < 99`` となり、緩和が発火して「再執筆する」が「警告通過」に反転していた。
    # 緩和は「threshold が既定値 ``DEFAULT_AUDIT_GATE_THRESHOLD`` のまま」のとき
    # だけ許可し、手動の厳格化があれば緩和しない。
    # 無効化は ``ENABLE_AUDIT_ADVISORY_STRICT_GUARD=false``。
    advisory = False
    advisory_reason = ""
    strict_guard = (
        is_advisory_strict_guard_enabled()
        and threshold > DEFAULT_AUDIT_GATE_THRESHOLD
        and get_advisory_threshold() == DEFAULT_AUDIT_ADVISORY_THRESHOLD
    )
    if (
        mode == "score_aggregation"
        and requires_regeneration
        and not critical_failure
        and failed
        and not strict_guard
        and get_advisory_threshold() < threshold
        and aggregate >= get_advisory_threshold()
        and all((o.get("effective_severity") in AUDIT_GATE_ADVISORY_SEVERITIES) for o in failed)
    ):
        advisory_threshold = get_advisory_threshold()
        requires_regeneration = False
        advisory = True
        advisory_reason = (
            f"総合スコア {round(aggregate, 2)} が advisory 閾値 "
            f"{advisory_threshold} 以上かつ失敗は "
            f"{'/'.join(AUDIT_GATE_ADVISORY_SEVERITIES)} のみのため警告通過"
        )

    return {
        "mode": mode,
        "aggregate_score": round(aggregate, 2),
        "threshold": threshold,
        "requires_regeneration": requires_regeneration,
        "critical_failure": critical_failure,
        "failed_count": len(failed),
        "scored_audit_ids": [o["audit_id"] for o in scored],
        "advisory": advisory,
        "advisory_reason": advisory_reason,
    }
