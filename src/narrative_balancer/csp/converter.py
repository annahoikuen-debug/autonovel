"""Converter from CP-SAT solution variables to domain Beat models."""

from typing import Dict, List, Optional
from ortools.sat.python import cp_model
from src.narrative_balancer.csp.variables import CSPVariables, INV_BEAT_TYPE_MAP
from src.narrative_balancer.models import Beat, BeatType


def csp_solution_to_beats(
    solver: cp_model.CpSolver,
    vars: CSPVariables,
    existing_beats: Optional[List[Beat]] = None,
) -> List[Beat]:
    """Map solved CP-SAT decision variables into Beat sequence.

    既存 Beat（確定済みエピソード）があれば、新しい Beat で置き換えず
    既存 Beat にソルバー由来の値を「差し込む」。差し込むのは
    tension / beat_type のみで、title / summary / characters /
    foreshadowing_setup / foreshadowing_payoff などの著作フィールドは
    必ず既存値を保持する（新規に生成したプレースホルダで上書きしない）。
    既存 Beat が無いエピソードのみ、プレースホルダの Beat を新規生成する。
    """
    existing_map: Dict[int, Beat] = {b.episode: b for b in (existing_beats or [])}
    beats: List[Beat] = []

    for i in range(vars.n_episodes):
        ep = i + 1
        t_val = float(solver.Value(vars.tension[i]))
        bt_int = solver.Value(vars.beat_type[i])
        beat_type = INV_BEAT_TYPE_MAP.get(bt_int, BeatType.SETUP)
        is_def = bool(solver.Value(vars.defeat[i]))

        base = existing_map.get(ep)
        if base is not None:
            # 確定済み Beat: 構造値だけ更新し、著作データは温存する。
            # is_defeat はモデルに制約が入っていないため既存値を優先する。
            merged = base.model_copy(deep=True)
            merged.tension = t_val
            merged.beat_type = beat_type
            beats.append(merged)
            continue

        chars_present = [ch for ch, presence in vars.char_presence.items() if solver.Value(presence[i])]

        beats.append(Beat(
            episode=ep,
            tension=t_val,
            beat_type=beat_type,
            title=f"第{ep}話",
            summary=f"ビート: {beat_type.value}",
            characters=chars_present,
            is_defeat=is_def,
        ))

    return beats
