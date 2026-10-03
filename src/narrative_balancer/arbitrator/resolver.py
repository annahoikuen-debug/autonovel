"""Priority-based conflict resolution and synthesis engine."""

import math
from typing import Dict, List, Tuple
from src.narrative_balancer.arbitrator.config import ArbitratorConfig
from src.narrative_balancer.arbitrator.models import BalancerResult, ConflictRecord, PlotState
from src.narrative_balancer.models import Beat, CorrectionAction


def _is_valid_tension(value: object) -> bool:
    """tension が比較可能な数値 (None/NaN でない) か判定する。"""
    if value is None:
        return False
    try:
        return not math.isnan(float(value))
    except (TypeError, ValueError):
        return False


def _is_placeholder_summary(summary: str) -> bool:
    """ソルバー/バランサーが生成したプレースホルダ summary かどうか。

    プレースホルダ (例: "ビート: SETUP") は著作データではないため、
    既存の著者サマリーを差し替えてはならない。
    """
    if summary.startswith("ビート:") or summary.startswith("Beat:"):
        return True
    if summary.startswith("第") and summary.endswith("話"):
        return True
    return False


class PriorityResolver:
    """Synthesizes narrative attributes using a domain-specific hierarchy:

    - Beat Type & Macro Structure: Grammar > CSP > DSP
    - Character Arc & Defeats: CSP > Grammar > DSP
    - Tension Dynamics & Curves: DSP > CSP > Grammar
    """

    def __init__(self, config: ArbitratorConfig):
        self.config = config
        self.priority_order = config.priority_order

    def resolve(
        self,
        original_state: PlotState,
        results: Dict[str, BalancerResult],
    ) -> Tuple[List[Beat], List[CorrectionAction], List[ConflictRecord]]:
        final_beats: List[Beat] = []
        applied_actions: List[CorrectionAction] = []
        conflicts: List[ConflictRecord] = []

        total_eps = original_state.total_episodes
        orig_map = {b.episode: b for b in original_state.beats}

        for ep in range(1, total_eps + 1):
            base_beat = orig_map.get(ep, Beat(episode=ep))

            # Active balancer proposals for this episode
            proposals: Dict[str, Beat] = {}
            for name, res in results.items():
                if res.success:
                    for b in res.beats:
                        if b.episode == ep:
                            proposals[name] = b
                            break

            if not proposals:
                final_beats.append(base_beat.model_copy(deep=True))
                continue

            # Determine if any balancer differs from base or each other
            has_difference = any(
                prop.tension != base_beat.tension
                or prop.beat_type != base_beat.beat_type
                or prop.characters != base_beat.characters
                or prop.is_defeat != base_beat.is_defeat
                for prop in proposals.values()
            )

            if not has_difference:
                final_beats.append(base_beat.model_copy(deep=True))
                continue

            # Synthesize specialized attributes
            chosen_beat = base_beat.model_copy(deep=True)
            conflicting_names = []

            # 1. Beat Type: Grammar (primary) -> CSP (secondary) -> DSP (tertiary)
            bt_order = ["grammar", "csp", "dsp"]
            for name in bt_order:
                if name in proposals:
                    prop_bt = proposals[name].beat_type
                    if prop_bt != base_beat.beat_type:
                        conflicting_names.append(name)
                    # The highest priority available sets the beat type
                    chosen_beat.beat_type = prop_bt
                    # summary は著作データ。_balancer 側のプレースホルダ/空文字で
                    # 上書きしない (既存著者テキストを保持)
                    proposed_summary = (proposals[name].summary or "").strip()
                    if proposed_summary and not _is_placeholder_summary(proposed_summary):
                        if not chosen_beat.summary.strip():
                            chosen_beat.summary = proposed_summary
                    break

            # 2. Tension: Take DSP if active and changed, or highest recommended tension
            dsp_tension = proposals["dsp"].tension if "dsp" in proposals else None
            if "dsp" in proposals and _is_valid_tension(dsp_tension) and dsp_tension != base_beat.tension:
                chosen_beat.tension = dsp_tension
                if "dsp" not in conflicting_names:
                    conflicting_names.append("dsp")
            else:
                # Max tension recommended by any balancer
                # tension は Optional[float] で None/NaN があり得るため除外する
                candidates = [
                    p.tension for p in proposals.values() if _is_valid_tension(p.tension)
                ]
                if candidates:
                    chosen_beat.tension = max(candidates)
                # 全部 None/NaN の場合は既存値 (base) をそのまま維持する

            # 3. Characters & Defeats: CSP (primary) -> Grammar -> Base
            # CSP は構造ソルバーであり、著作データ (characters) と
            # 確定済みエピソードの is_defeat の正誤を決める権限はない。
            # 既存 Beat が無いエピソード (新規生成) のときだけ採用する。
            if "csp" in proposals and orig_map.get(ep) is None:
                if proposals["csp"].characters:
                    chosen_beat.characters = list(proposals["csp"].characters)
                chosen_beat.is_defeat = proposals["csp"].is_defeat

            final_beats.append(chosen_beat)

            # Record action
            if chosen_beat.beat_type != base_beat.beat_type or chosen_beat.tension != base_beat.tension:
                primary_winner = conflicting_names[0] if conflicting_names else "integrated"
                action = CorrectionAction(
                    episode=ep,
                    action_type=f"{primary_winner.upper()}_SYNTHESIZED_APPLY",
                    target_field="beat",
                    original_value=base_beat.beat_type.value,
                    new_value=chosen_beat.beat_type.value,
                    reason=f"Synthesized from {', '.join(proposals.keys())} with {primary_winner} priority",
                )
                applied_actions.append(action)

                if len(conflicting_names) > 1:
                    conflicts.append(ConflictRecord(
                        episode=ep,
                        conflicting_balancers=conflicting_names,
                        winning_balancer=primary_winner,
                        chosen_action=action,
                        rationale="Synthesized attributes according to domain expertise: Grammar for structure, CSP for arcs, DSP for tension.",
                    ))

        return final_beats, applied_actions, conflicts
