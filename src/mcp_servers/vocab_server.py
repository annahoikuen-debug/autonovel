"""Sensory Vocabulary MCP Server Implementation (JSON-RPC)."""
from __future__ import annotations

from typing import Any, Dict
from src.mcp_servers.providers.vocab_provider import SensoryVocabProvider
from src.mcp_servers.vocab_schemas import SensoryWord


class VocabMCPServer:
    """感覚・レトリック辞書を提供する MCP サーバー実装クラス"""

    def __init__(self, provider: SensoryVocabProvider) -> None:
        self.provider = provider

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC形式のリクエストを処理する"""
        method = request_data.get("method")
        params = request_data.get("params", {})
        req_id = request_data.get("id", 1)

        try:
            if method == "register_words":
                genre = params.get("genre", "general")
                raw_words = params.get("words", [])
                words = [SensoryWord(**w) if isinstance(w, dict) else w for w in raw_words]
                self.provider.register_words(genre, words)
                return {"jsonrpc": "2.0", "result": {"status": "success"}, "id": req_id}

            elif method == "suggest_metaphors":
                keyword = params.get("keyword", "")
                genre = params.get("genre", "general")
                suggestions = self.provider.suggest_metaphors(keyword, genre)
                return {"jsonrpc": "2.0", "result": {"suggestions": suggestions}, "id": req_id}

            elif method == "resources/list":
                resources = []
                for genre in self.provider.vocab_sets.keys():
                    resources.append({
                        "uri": f"novel://vocab/sensory/{genre}",
                        "name": f"Sensory Vocabulary for {genre.capitalize()}",
                    })
                return {"jsonrpc": "2.0", "result": {"resources": resources}, "id": req_id}

            elif method == "resources/read":
                uri = params.get("uri", "")
                content = self.provider.read_resource(uri)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "contents": [{"uri": uri, "mimeType": "text/plain", "text": content}]
                    },
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
