"""Scene Transition MCP Server Implementation (JSON-RPC)."""
from __future__ import annotations

from typing import Any, Dict
from src.mcp_servers.providers.transition_provider import SceneTransitionValidator
from src.mcp_servers.transition_schemas import SceneState


class TransitionMCPServer:
    """シーン間整合性・矛盾検知ツールを提供する MCP サーバー実装クラス"""

    def __init__(self, validator: SceneTransitionValidator) -> None:
        self.validator = validator

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC形式のリクエストを処理する"""
        method = request_data.get("method")
        params = request_data.get("params", {})
        req_id = request_data.get("id", 1)

        try:
            if method == "validate_scene_transition":
                from_data = params.get("from_state", {})
                to_data = params.get("to_state", {})
                from_state = SceneState(**from_data)
                to_state = SceneState(**to_data)

                res = self.validator.validate_transition(from_state, to_state)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "is_valid": res.is_valid,
                        "conflicts": [
                            {
                                "conflict_type": c.conflict_type,
                                "message": c.message,
                                "severity": c.severity,
                            }
                            for c in res.conflicts
                        ],
                        "patch_suggestions": res.patch_suggestions,
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
