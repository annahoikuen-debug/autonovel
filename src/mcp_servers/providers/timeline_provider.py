"""Timeline Resource Provider for managing timelines and episode digests."""
from __future__ import annotations

from typing import Dict, List
from src.mcp_servers.timeline_schemas import (
    TimelineEvent,
    EpisodeDigest,
    parse_memory_uri,
)


class TimelineResourceProvider:
    """タイムラインおよびエピソード要約を管理し、URIリソースとして提供するプロバイダー"""

    def __init__(self) -> None:
        self.events: List[TimelineEvent] = []
        self.digests: Dict[int, EpisodeDigest] = {}

    def add_timeline_event(self, event: TimelineEvent) -> None:
        """タイムラインイベントを追加する"""
        self.events.append(event)

    def record_episode_digest(self, digest: EpisodeDigest) -> None:
        """エピソード要約を登録する"""
        self.digests[digest.episode_num] = digest

    def read_resource(self, uri: str) -> str:
        """MCPリソースURIに対応するコンテンツを文字列として返却する"""
        parsed = parse_memory_uri(uri)
        res_type = parsed.get("type")

        if res_type == "timeline":
            if not self.events:
                return "No timeline events recorded."
            lines = []
            for ev in self.events:
                chars = ", ".join(ev.characters) if ev.characters else "None"
                lines.append(f"[{ev.timestamp}] ({ev.location}) {ev.description} [Chars: {chars}]")
            return "\n".join(lines)

        elif res_type == "episode_digest":
            ep_num = parsed.get("episode_num")
            digest = self.digests.get(ep_num)
            if not digest:
                return f"Episode {ep_num} digest not found."
            footholds = ", ".join(digest.footholds_or_foreshadowings) or "None"
            return (
                f"=== Episode {digest.episode_num} Digest ===\n"
                f"Summary: {digest.summary}\n"
                f"Foreshadowings/Footholds: {footholds}"
            )

        return f"Resource not found or unsupported URI: {uri}"
