"""Tension and Emotion MCP Server Implementation (JSON-RPC)."""
from __future__ import annotations

from typing import Any, Dict
from src.mcp_servers.providers.tension_provider import TensionAnalyzer


class TensionMCPServer:
    """感情曲線＆テンション波形測定ツールを提供する MCP サーバー実装クラス"""

    def __init__(self, analyzer: TensionAnalyzer) -> None:
        self.analyzer = analyzer

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC形式のリクエストを処理する"""
        method = request_data.get("method")
        params = request_data.get("params", {})
        req_id = request_data.get("id", 1)

        try:
            if method == "check_emotional_tension":
                text = params.get("text", "")
                target_tension = params.get("target_tension")

                res = self.analyzer.calculate_tension(text, target_tension=target_tension)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "tension_score": res.tension_score,
                        "polarity": res.polarity,
                        "dominant_emotion": res.dominant_emotion,
                        "feedback": res.feedback,
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
