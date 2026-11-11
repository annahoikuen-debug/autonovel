"""Ensemble judge integrating 3 non-LLM layers (+ optional 4th LLM vote) to reach final resolution decisions."""

import logging
from typing import Any, Optional

from src.models.ensemble_foreshadowing import EnsembleJudgment, EnsembleScoreBreakdown
from src.models.predicate_match import PredicateAnalysisResult
from src.models.writing_metadata import ForeshadowingReport
from src.engine.nlp.predicate_scorer import PredicateScorer

logger = logging.getLogger(__name__)

# PredicateScorer.calculate_score の生スコア上限 (resolved=25*conf / progressed=15*conf)
SYNTAX_RAW_MAX = 25


class EnsembleJudge:
    """Evaluates foreshadowing resolution using zero-LLM ensemble voting.

    PLAN_S1 P3: 任意の第 4 票 (``llm_vote``) と SSOT 配点 (``weights`` / ``thresholds``)
    を受け付ける。**既存の 4 引数呼び出し (llm_vote/weights/thresholds を渡さない) は
    従来どおり完全に同一の判定を返す** (Q9 ``test_legacy_signature_unchanged`` 契約)。

    metadata 自己申告だけで RESOLVED 閾値に到達できる構造 (PLAN_S1 G-3) は、
    mainline モードの新配点 (metadata 30 + 契約 35 = 65 < 75) で緩和される。
    """

    RESOLVED_THRESHOLD = 75
    PROGRESSED_THRESHOLD = 35

    # legacy 配点 (現行動作)。
    # SSOT (config/audit_calibration.yaml foreshadowing.weights) が明示された場合のみ上書き。
    LEGACY_WEIGHTS = {"contract": 35, "metadata": 40, "syntax": 25, "llm_vote": 0}

    @classmethod
    def evaluate(
        cls,
        foreshadowing_id: int,
        is_contracted: bool,
        metadata_report: Optional[ForeshadowingReport],
        syntax_analysis: Optional[PredicateAnalysisResult],
        llm_vote: Optional[Any] = None,
        weights: Optional[dict] = None,
        thresholds: Optional[dict] = None,
    ) -> EnsembleJudgment:
        """
        Evaluate resolution for a single foreshadowing item.

        Args:
            foreshadowing_id: ID of the evaluated foreshadowing
            is_contracted: Whether this item was contracted in the episode beat sheet (legacy: 35 pts)
            metadata_report: Report from LLM co-generation metadata (legacy: up to 40 pts)
            syntax_analysis: Syntactic predicate analysis result (legacy: up to 25 pts)
            llm_vote: PLAN_S1 P3 — 第 4 票 (``LLMVoteResult`` 相当の ``action`` 属性を持つ
                オブジェクト)。None = 投票なし (現行動作 / P1 既定)。
            weights: PLAN_S1 P3 — 配点 dict (contract/metadata/syntax/llm_vote)。
                None は legacy 配点 (35/40/25/0)。
            thresholds: PLAN_S1 P3 — 閾値 dict (resolved/progressed/
                no_metadata_resolved/no_metadata_progressed)。None は legacy 閾値
                (75/35、metadata 欠損時 55/15)。

        Returns:
            EnsembleJudgment with breakdown, status, and rationale
        """
        w = {**cls.LEGACY_WEIGHTS, **(weights or {})}
        if thresholds:
            t_resolved = int(thresholds.get("resolved", cls.RESOLVED_THRESHOLD))
            t_progressed = int(thresholds.get("progressed", cls.PROGRESSED_THRESHOLD))
            nm_resolved = int(thresholds.get("no_metadata_resolved", 55))
            nm_progressed = int(thresholds.get("no_metadata_progressed", 15))
        else:
            t_resolved, t_progressed = cls.RESOLVED_THRESHOLD, cls.PROGRESSED_THRESHOLD
            nm_resolved, nm_progressed = 55, 15

        # 1. Contract Score
        contract_score = w["contract"] if is_contracted else 0

        # 2. Metadata Report Score (自己申告 — 過大申告リスクは PLAN_S1 G-3 / P4 で実測)
        metadata_max = w["metadata"]
        metadata_score = 0
        if metadata_report:
            if metadata_report.action == "resolved":
                metadata_score = metadata_max
            elif metadata_report.action == "progressed":
                metadata_score = metadata_max // 2
            elif metadata_report.action == "mentioned_only":
                metadata_score = 0

        # 3. Syntax Score (生 0-25 を配点へ線形スケール。legacy では恒等変換)
        syntax_score = 0
        if syntax_analysis:
            raw = PredicateScorer.calculate_score(syntax_analysis)
            syntax_score = int(round(raw * w["syntax"] / SYNTAX_RAW_MAX))

        # 4. LLM Vote Score (PLAN_S1 P3: resolved=満点 / progressed=半分 / unmentioned=0)
        llm_action = getattr(llm_vote, "action", None) if llm_vote is not None else None
        llm_score = 0
        if llm_action == "resolved":
            llm_score = w["llm_vote"]
        elif llm_action == "progressed":
            llm_score = w["llm_vote"] // 2

        # Total score
        total_score = contract_score + metadata_score + syntax_score + llm_score

        # Determine effective thresholds based on metadata availability
        has_metadata = metadata_report is not None
        resolved_threshold = t_resolved if has_metadata else nm_resolved
        progressed_threshold = t_progressed if has_metadata else nm_progressed

        # Determine status
        if total_score >= resolved_threshold:
            status = "RESOLVED"
            should_reschedule = False
            rationale = (
                f"Resolved with ensemble consensus ({total_score} pts: "
                f"Contract={contract_score}, Metadata={metadata_score}, Syntax={syntax_score}"
                f", LLM={llm_score})"
            )
        elif total_score >= progressed_threshold:
            status = "PROGRESSED"
            should_reschedule = True
            rationale = (
                f"Progressed but not fully resolved ({total_score} pts: "
                f"Contract={contract_score}, Metadata={metadata_score}, Syntax={syntax_score}"
                f", LLM={llm_score})"
            )
        else:
            status = "PLANTED"
            should_reschedule = is_contracted  # If contracted but not addressed, must reschedule
            rationale = (
                f"Remains planted/unresolved ({total_score} pts: "
                f"Contract={contract_score}, Metadata={metadata_score}, Syntax={syntax_score}"
                f", LLM={llm_score})"
            )

        breakdown = EnsembleScoreBreakdown(
            contract_score=contract_score,
            metadata_score=metadata_score,
            syntax_score=syntax_score,
            total_score=total_score,
            llm_vote_score=llm_score,
        )

        return EnsembleJudgment(
            foreshadowing_id=foreshadowing_id,
            status=status,
            score_breakdown=breakdown,
            rationale=rationale,
            should_reschedule=should_reschedule,
        )
