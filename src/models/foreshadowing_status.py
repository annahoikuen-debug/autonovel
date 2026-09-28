"""ForeshadowingStatus Enum定義。

伏線ステートマシンの状態遷移を定義する。
状態遷移: PLANTED → PROGRESSED → RESOLVED
                 └→ ABANDONED（回収放棄）
"""
from enum import Enum


class ForeshadowingStatus(str, Enum):
    PLANTED = "planted"        # 伏線設置済み（未回収）
    PROGRESSED = "progressed"  # 進展・匂わせ中
    RESOLVED = "resolved"      # 回収完了
    ABANDONED = "abandoned"    # 回収放棄

    @classmethod
    def active_statuses(cls) -> list["ForeshadowingStatus"]:
        """未回収として扱うステータス一覧を返す"""
        return [cls.PLANTED, cls.PROGRESSED]

    @classmethod
    def _transition_table(cls) -> dict["ForeshadowingStatus", frozenset["ForeshadowingStatus"]]:
        """許可された状態遷移テーブル（v5.3 伏線ステートマシン実体化）

        - PLANTED / PROGRESSED → PROGRESSED / RESOLVED / ABANDONED
        - PLANTED → PLANTED と同じ状態への再設定は不可（誤った再設置防止）
        - RESOLVED / ABANDONED は終端状態のため遷移不可（回収済み伏線の巻き戻しは事故）
        """
        return {
            cls.PLANTED: frozenset({cls.PROGRESSED, cls.RESOLVED, cls.ABANDONED}),
            cls.PROGRESSED: frozenset({cls.RESOLVED, cls.ABANDONED}),
            cls.RESOLVED: frozenset(),
            cls.ABANDONED: frozenset(),
        }

    @classmethod
    def can_transition(
        cls, current: "ForeshadowingStatus | str", target: "ForeshadowingStatus | str"
    ) -> bool:
        """状態遷移が許可されるかを判定する"""
        try:
            cur = cls(current) if not isinstance(current, cls) else current
            nxt = cls(target) if not isinstance(target, cls) else target
        except ValueError:
            return False
        return nxt in cls._transition_table().get(cur, frozenset())

    @classmethod
    def allowed_transitions(cls, current: "ForeshadowingStatus | str") -> frozenset["ForeshadowingStatus"]:
        """現在の状態から遷移可能な状態の集合を返す"""
        try:
            cur = cls(current) if not isinstance(current, cls) else current
        except ValueError:
            return frozenset()
        return cls._transition_table().get(cur, frozenset())

    @property
    def is_active(self) -> bool:
        """まだ回収されていない（アクティブ）かどうか"""
        return self in (ForeshadowingStatus.PLANTED, ForeshadowingStatus.PROGRESSED)

    @property
    def is_resolved(self) -> bool:
        """回収完了状態かどうか"""
        return self == ForeshadowingStatus.RESOLVED

    @property
    def is_terminal(self) -> bool:
        """終端状態（RESOLVED or ABANDONED）かどうか"""
        return self in (ForeshadowingStatus.RESOLVED, ForeshadowingStatus.ABANDONED)


class ForeshadowingScope(str, Enum):
    SHORT_TERM = "short_term"  # 即時快感用（2〜3話以内の伏線）
    LONG_TERM = "long_term"    # 1巻伏線（クライマックスで回収）
