"""Timeline MCP Server Implementation (JSON-RPC)."""

from __future__ import annotations

from typing import Any, Dict
from src.mcp_servers.providers.timeline_provider import TimelineResourceProvider
from src.mcp_servers.timeline_schemas import TimelineEvent, EpisodeDigest


class TimelineMCPServer:
    """3層ローリング記憶＆タイムラインを提供する MCP サーバー実装クラス"""

    def __init__(self, provider: TimelineResourceProvider) -> None:
        self.provider = provider

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC形式のリクエストを処理する"""
        method = request_data.get("method")
        params = request_data.get("params", {})
        req_id = request_data.get("id", 1)

        try:
            if method == "add_timeline_event":
                event = TimelineEvent(**params)
                self.provider.add_timeline_event(event)
                return {"jsonrpc": "2.0", "result": {"status": "success"}, "id": req_id}

            elif method == "record_episode_digest":
                digest = EpisodeDigest(**params)
                self.provider.record_episode_digest(digest)
                return {"jsonrpc": "2.0", "result": {"status": "success"}, "id": req_id}

            elif method == "resources/list":
                # 固定で対応リソース一覧を返す
                resources = [
                    {"uri": "novel://memory/timeline", "name": "Global Timeline"},
                ]
                for ep_num in self.provider.digests.keys():
                    resources.append(
                        {
                            "uri": f"novel://memory/episode/{ep_num}/digest",
                            "name": f"Episode {ep_num} Digest",
                        }
                    )
                return {"jsonrpc": "2.0", "result": {"resources": resources}, "id": req_id}

            elif method == "resources/read":
                uri = params.get("uri", "")
                content = self.provider.read_resource(uri)
                return {
                    "jsonrpc": "2.0",
                    "result": {"contents": [{"uri": uri, "mimeType": "text/plain", "text": content}]},
                    "id": req_id,
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": req_id,
                }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": req_id,
            }
