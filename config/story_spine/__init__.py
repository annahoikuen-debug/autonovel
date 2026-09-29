"""STORY_SPINE: 構造テンプレート層の公開 API（契約凍結 2026-09-29）。

TRACK-A / TRACK-B の双方が依存する門。.plan_f1 §0.2 の排他所有表に従い、
- A 所有: beat.py / loader.py / patterns.yaml / lengths.yaml / markets.yaml / cards.yaml
- B 所有: genre_registry.py（A は作らない）

NOTE: `resolve_spine` は **A3 で追加される**。それまで import すると ImportError になるため、
      本ファイルでは re-export しない。参照側は `from services.spine_resolver import resolve_spine`。
"""

from .beat import ARTIFACTS, BEAT_VOCABULARY, ROLES, Beat, BeatInstance, Spine
from .loader import (
    BASE_DIR,
    CARDS,
    LENGTHS,
    MARKETS,
    PATTERNS,
    get_card,
    get_length,
    get_market,
    get_pattern,
)

__all__ = [
    "ARTIFACTS",
    "BASE_DIR",
    "BEAT_VOCABULARY",
    "CARDS",
    "LENGTHS",
    "MARKETS",
    "PATTERNS",
    "ROLES",
    "Beat",
    "BeatInstance",
    "Spine",
    "get_card",
    "get_length",
    "get_market",
    "get_pattern",
]


def __getattr__(name: str):
    """`resolve_spine` は A3 で `services.spine_resolver` に実装された。

    `services.spine_resolver` も同じ `config.story_spine` パッケージを import するため、
    import 時に再エクスポートすると循環になる。PEP 562 の遅延解決で回避する。
    """
    if name == "resolve_spine":
        from src.services.spine_resolver import resolve_spine

        return resolve_spine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
