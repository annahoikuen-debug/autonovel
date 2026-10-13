"""Scene Transition Validator Provider for Continuity and Consistency Checks."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from src.mcp_servers.transition_schemas import (
    SceneState,
    TransitionConflict,
    TransitionValidationResult,
)

# デフォルトの瞬間移動禁止ペア（Dungeon -> Royal Castle 等の遠距離移動）
DEFAULT_FORBIDDEN_INSTANT_MOVES: List[Tuple[str, str]] = [
    ("Dungeon", "Royal Castle"),
]


class SceneTransitionValidator:
    """前後のシーン状態間の連続性・整合性を検証するバリデータ

    ユーザー定義ルール（allowed_transitions / forbidden_instant_moves）を
    コンストラクタで受け取れる。未指定の場合はデフォルトルールを適用する。
    """

    def __init__(
        self,
        allowed_transitions: Optional[Dict[str, List[str]]] = None,
        forbidden_instant_moves: Optional[List[Tuple[str, str]]] = None,
        enforce_remote_metadata_rule: bool = True,
    ) -> None:
        """Args:
        allowed_transitions: 場所ごとの許可された直接遷移マップ（from -> [to, ...]）。
            指定された場合、このマップに含まれない遷移は travel_method または
            Teleport タグが必要になる。
        forbidden_instant_moves: 瞬間移動が禁止されている (from, to) の場所ペア。
            未指定の場合は DEFAULT_FORBIDDEN_INSTANT_MOVES を使用する。
            空リストを渡した場合はデフォルトルールを含め無効化する。
        enforce_remote_metadata_rule: to_state.metadata の distance_category == "remote"
            かつ travel_method 未指定の場合にコンフリクトを検出する汎用ルールの有効化。
        """
        if forbidden_instant_moves is None:
            self.forbidden_instant_moves: List[Tuple[str, str]] = list(
                DEFAULT_FORBIDDEN_INSTANT_MOVES
            )
        else:
            self.forbidden_instant_moves = list(forbidden_instant_moves)
        self.allowed_transitions = allowed_transitions
        self.enforce_remote_metadata_rule = enforce_remote_metadata_rule

    def validate_transition(
        self, from_state: SceneState, to_state: SceneState
    ) -> TransitionValidationResult:
        """前シーン (from_state) から現シーン (to_state) への状態変化を検証する"""
        conflicts: List[TransitionConflict] = []
        patches: List[str] = []

        # 1. 所在矛盾チェック
        if from_state.character_name == to_state.character_name:
            if from_state.location != to_state.location:
                has_travel = bool(to_state.metadata.get("travel_method"))
                has_teleport_tag = "Teleport" in to_state.metadata.get("tags", [])

                # 1a. ユーザー定義 / デフォルトの瞬間移動禁止ペア
                pair = (from_state.location, to_state.location)
                if pair in self.forbidden_instant_moves and not has_travel and not has_teleport_tag:
                    conflicts.append(
                        TransitionConflict(
                            conflict_type="location",
                            message=(
                                f"Instantaneous movement from {from_state.location} "
                                f"to {to_state.location} without Teleport is implausible."
                            ),
                            severity="error",
                        )
                    )
                    patches.append(
                        "Add travel transition scene or teleport explanation between "
                        f"{from_state.location} and {to_state.location}."
                    )

                # 1b. 許可遷移マップによる汎用チェック
                if self.allowed_transitions is not None:
                    allowed = self.allowed_transitions.get(from_state.location, [])
                    if to_state.location not in allowed and not has_travel and not has_teleport_tag:
                        conflicts.append(
                            TransitionConflict(
                                conflict_type="location",
                                message=(
                                    f"Transition from {from_state.location} to "
                                    f"{to_state.location} is not in allowed_transitions "
                                    "and no travel method is described."
                                ),
                                severity="error",
                            )
                        )
                        patches.append(
                            f"Describe travel from {from_state.location} to "
                            f"{to_state.location}, or add it to allowed_transitions."
                        )

                # 1c. 汎用メタデータルール: 遠距離移動なのに移動手段の記述がない
                if (
                    self.enforce_remote_metadata_rule
                    and to_state.metadata.get("distance_category") == "remote"
                    and not has_travel
                    and not has_teleport_tag
                ):
                    conflicts.append(
                        TransitionConflict(
                            conflict_type="location",
                            message=(
                                f"Remote movement from {from_state.location} to "
                                f"{to_state.location} lacks a travel_method in metadata."
                            ),
                            severity="warning",
                        )
                    )
                    patches.append(
                        "Add travel_method metadata or a travel scene for the remote transition."
                    )

        # 2. 所持品矛盾チェック (例: 持っていなかったアイテムが突然使用されているなど)
        for item in to_state.inventory:
            if item not in from_state.inventory and item not in ["Basic Clothes", "Hands"]:
                # 前のシーンで所持しておらず、新しく入手した描写がない場合
                if not to_state.metadata.get("item_acquired", False):
                    conflicts.append(
                        TransitionConflict(
                            conflict_type="inventory",
                            message=f"Character {to_state.character_name} uses item '{item}' without acquiring it in previous scenes.",
                            severity="warning"
                        )
                    )
                    patches.append(f"Insert an item acquisition event for '{item}'.")

        # 3. 負傷状態の矛盾チェック (重傷から突然無傷に復帰)
        if from_state.status == "critical_injured" and to_state.status == "normal":
            if not to_state.metadata.get("healed", False):
                conflicts.append(
                    TransitionConflict(
                        conflict_type="status",
                        message=f"Character {to_state.character_name} recovered from critical injury to normal instantly without healing.",
                        severity="error"
                    )
                )
                patches.append("Add a healing magic or resting scene before returning to normal status.")

        is_valid = len([c for c in conflicts if c.severity == "error"]) == 0

        return TransitionValidationResult(
            is_valid=is_valid,
            conflicts=conflicts,
            patch_suggestions=patches,
        )
