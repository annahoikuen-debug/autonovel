from __future__ import annotations

"""Shadow モード監査 (M5-B)。

ENABLE_PAIRWISE_SHADOW (gate.pairwise.shadow_enabled) が true のとき、
旧絶対ゲートで合否を決定しつつ、ペアワイズ判定結果を
AuditRun(judge_mode="shadow") に並行記録する。
合否への影響はゼロ（キルスイッチ付き）。
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from src.agents.specialists.unified_auditor import (
    UnifiedAuditor,
    UnifiedAuditReport,
)
from src.audit.calibration_store import is_pairwise_shadow_enabled
from src.audit.judge_panel import JudgePanel, PairwiseVerdict


@dataclass
class ShadowAuditResult:
    """シャドウ監査結果。"""

    main_report: UnifiedAuditReport
    pairwise_verdict: PairwiseVerdict | None
    shadow_enabled: bool
    judge_mode: str


async def run_shadow_audit(
    auditor: UnifiedAuditor,
    panel: JudgePanel,
    text: str,
    *,
    db_session: Any = None,
    book_id: int = 0,
    ep_num: int = 0,
    anchor_text: str | None = None,
    axis: str = "overall",
    provenance_family: str | None = None,
) -> ShadowAuditResult:
    """シャドウ監査を実行する。

    1. 旧絶対ゲート (UnifiedAuditor.audit) で合否を決定（本番）
    2. ペアワイズ判定を並行実行（shadow、合否に影響なし）
    3. 両方の結果を AuditRun に judge_mode="shadow" で記録

    Args:
        auditor: UnifiedAuditor インスタンス
        panel: JudgePanel インスタンス
        text: 監査対象本文
        db_session: SQLAlchemy セッション (AuditRun 永続化用)
        book_id / ep_num: 作品・話番号
        anchor_text: ペアワイズ比較のアンカー原稿 (None の場合はペアワイズをスキップ)
        axis: 評価軸
        provenance_family: 出力原稿のモデル family (自己偏好除外用)

    Returns:
        ShadowAuditResult
    """
    shadow_enabled = is_pairwise_shadow_enabled()

    # Step 1: 旧絶対ゲートで合否を決定（本番、影響なし）
    main_report = await auditor.audit(
        text,
        db_session=db_session,
        book_id=book_id,
        ep_num=ep_num,
    )

    # Step 2: ペアワイズ判定（shadow、合否に影響なし）
    pairwise_verdict: PairwiseVerdict | None = None
    if shadow_enabled and anchor_text is not None:
        try:
            pairwise_verdict = await panel.pairwise(
                anchor_text,
                text,
                axis=axis,
                provenance_family=provenance_family,
            )
        except Exception:  # noqa: BLE001 - シャドウは失敗しても本番に影響しない
            pairwise_verdict = None

    # Step 3: シャドウ用の AuditRun を追加記録（judge_mode="shadow"）
    # 旧ゲートとは別に judge_mode="shadow" で記録し、後続の一致率分析に使用する。
    # 合否は旧ゲート (main_report) が決定し、shadow レコードは参照専用。
    if shadow_enabled and db_session is not None:
        try:
            await auditor.audit(
                text,
                db_session=db_session,
                book_id=book_id,
                ep_num=ep_num,
                judge_mode="shadow",
            )
        except Exception:  # noqa: BLE001 - シャドウ記録の失敗は本番に影響しない
            pass

    judge_mode = "shadow" if shadow_enabled else "single"

    return ShadowAuditResult(
        main_report=main_report,
        pairwise_verdict=pairwise_verdict,
        shadow_enabled=shadow_enabled,
        judge_mode=judge_mode,
    )


async def run_shadow_pairwise_only(
    panel: JudgePanel,
    anchor_text: str,
    challenger_text: str,
    axis: str = "overall",
    provenance_family: str | None = None,
) -> PairwiseVerdict | None:
    """シャドウ用ペアワイズ判定のみを実行する（失敗時は None）。"""
    if not is_pairwise_shadow_enabled():
        return None
    try:
        return await panel.pairwise(
            anchor_text,
            challenger_text,
            axis=axis,
            provenance_family=provenance_family,
        )
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "ShadowAuditResult",
    "run_shadow_audit",
    "run_shadow_pairwise_only",
]
