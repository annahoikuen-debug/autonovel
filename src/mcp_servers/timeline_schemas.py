"""Timeline and Episode Digest Schemas and URI Parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Any
import re


@dataclass
class TimelineEvent:
    """タイムラインイベント定義"""

    timestamp: str
    location: str
    description: str
    characters: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EpisodeDigest:
    """エピソード要約定義"""

    episode_num: int
    summary: str
    footholds_or_foreshadowings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def parse_memory_uri(uri: str) -> Dict[str, Any]:
    """
    MCPリソースURIを解析する。
    対応URI:
      - novel://memory/timeline
      - novel://memory/episode/{n}/digest
    """
    if uri == "novel://memory/timeline":
        return {"type": "timeline"}

    match = re.match(r"^novel://memory/episode/(\d+)/digest$", uri)
    if match:
        episode_num = int(match.group(1))
        return {"type": "episode_digest", "episode_num": episode_num}

    return {"type": "unknown", "uri": uri}
