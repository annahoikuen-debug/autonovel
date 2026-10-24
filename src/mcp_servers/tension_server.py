"""Tension and Emotion MCP Server Implementation (JSON-RPC 2.0)."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict

from src.mcp_servers.providers.tension_provider import TensionAnalyzer

logger = logging.getLogger(__name__)


class TensionMCPServer:
    """感情曲線＆テンション波形測定・制御ツールを提供する MCP サーバー実装クラス"""

    def __init__(self, analyzer: TensionAnalyzer | None = None) -> None:
        self.analyzer = analyzer or TensionAnalyzer()

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
                    "result": res.model_dump(),
                    "id": req_id,
                }
            elif method == "generate_target_curve":
                curve_type = params.get("curve_type", "climax_catharsis")
                curve_res = self.analyzer.generate_target_curve(curve_type=curve_type)
                return {
                    "jsonrpc": "2.0",
                    "result": curve_res.model_dump(),
                    "id": req_id,
                }
            elif method == "analyze_novel_arc":
                text = params.get("text", "")
                curve_type = params.get("curve_type", "climax_catharsis")
                custom_targets = params.get("custom_targets")
                analysis_res = self.analyzer.analyze_novel_arc(
                    text=text,
                    curve_type=curve_type,
                    custom_targets=custom_targets,
                )
                return {
                    "jsonrpc": "2.0",
                    "result": analysis_res.model_dump(),
                    "id": req_id,
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": req_id,
                }
        except Exception as e:
            logger.exception("Error in TensionMCPServer: %s", e)
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": req_id,
            }

    def run_stdio(self) -> None:
        """標準入出力ベースのメインループ"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                res = self.handle_request(req)
                print(json.dumps(res, ensure_ascii=False))
                sys.stdout.flush()
            except json.JSONDecodeError:
                err = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": "Parse error"},
                    "id": None,
                }
                print(json.dumps(err))
                sys.stdout.flush()


if __name__ == "__main__":
    server = TensionMCPServer()
    server.run_stdio()
