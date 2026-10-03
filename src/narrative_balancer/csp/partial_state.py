"""Partial plot state representation for minimal-change narrative repair."""

from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field, ConfigDict
from src.narrative_balancer.models import Beat


class PartialPlotState(BaseModel):
    """Encapsulates confirmed episodes and undetermined episodes."""
    model_config = ConfigDict(extra="ignore")

    total_episodes: int = Field(default=40, ge=1)
    confirmed_beats: Dict[int, Beat] = Field(default_factory=dict, description="1-based episode mapping")
    unconfirmed_episodes: Set[int] = Field(default_factory=set)

    @classmethod
    def from_beats(cls, beats: List[Beat], total_episodes: Optional[int] = None) -> "PartialPlotState":
        total = total_episodes or (max((b.episode for b in beats), default=40))
        confirmed = {b.episode: b for b in beats}
        all_eps = set(range(1, total + 1))
        unconfirmed = all_eps - set(confirmed.keys())
        return cls(total_episodes=total, confirmed_beats=confirmed, unconfirmed_episodes=unconfirmed)

    def merge_solution(self, solved_beats: List[Beat]) -> "PartialPlotState":
        """Merge solved beats into this state, completing unconfirmed episodes.

        確定済みエピソードは「置き換え」ずに統合する。ソルバーが所有する
        tension / beat_type のみ反映し、title / summary / characters /
        is_defeat / foreshadowing などの著作データは既存値を保持する。
        ソルバー結果に無い確定済みエピソードは削除せずそのまま残す。
        """
        new_confirmed = {ep: beat.model_copy(deep=True) for ep, beat in self.confirmed_beats.items()}
        for b in solved_beats:
            prev = new_confirmed.get(b.episode)
            if prev is not None:
                merged = prev.model_copy(deep=True)
                merged.tension = b.tension
                merged.beat_type = b.beat_type
                if not merged.foreshadowing_setup and b.foreshadowing_setup:
                    merged.foreshadowing_setup = list(b.foreshadowing_setup)
                if not merged.foreshadowing_payoff and b.foreshadowing_payoff:
                    merged.foreshadowing_payoff = list(b.foreshadowing_payoff)
                new_confirmed[b.episode] = merged
            else:
                new_confirmed[b.episode] = b.model_copy(deep=True)

        remaining = set(range(1, self.total_episodes + 1)) - set(new_confirmed.keys())
        return PartialPlotState(
            total_episodes=self.total_episodes,
            confirmed_beats=new_confirmed,
            unconfirmed_episodes=remaining,
        )

    def to_beat_list(self) -> List[Beat]:
        """Convert state to an ordered list of beats sorted by episode number."""
        return [self.confirmed_beats[ep] for ep in sorted(self.confirmed_beats.keys())]
