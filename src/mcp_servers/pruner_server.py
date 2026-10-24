"""Context Pruning MCP Server Implementation (JSON-RPC 2.0 / Tool Provider)."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict

from src.mcp_servers.providers.pruning_provider import ContextPruningProvider
from src.mcp_servers.pruning_schemas import PruneContextRequest

logger = logging.getLogger(__name__)


class PrunerMCPServer:
    """Context Pruning MCP Server (動的コンテキスト・プルーニング サーバー)"""

    def __init__(self, provider: ContextPruningProvider | None = None) -> None:
        self.provider = provider or ContextPruningProvider()

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC形式のリクエストを処理する"""
        method = request_data.get("method")
        params = request_data.get("params", {})
        req_id = request_data.get("id", 1)

        try:
            if method == "prune_context":
                req = PruneContextRequest(**params)
                result = self.provider.prune_context(req)
                return {
                    "jsonrpc": "2.0",
                    "result": result.model_dump(),
                    "id": req_id,
                }
            elif method == "prune_characters":
                plot = params.get("plot_blueprint", "")
                characters = params.get("characters", [])
                pov = params.get("pov_character")
                active, peripheral, excluded = self.provider._filter_characters(
                    characters=characters,
                    plot=plot,
                    pov_character=pov,
                )
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "active_characters": active,
                        "peripheral_characters": peripheral,
                        "excluded_characters": excluded,
                    },
                    "id": req_id,
                }
            elif method == "prune_lore":
                plot = params.get("plot_blueprint", "")
                world_lore = params.get("world_lore", [])
                active_names = set(params.get("active_character_names", []))
                relevant = self.provider._filter_lore(
                    world_lore=world_lore,
                    plot=plot,
                    active_character_names=active_names,
                )
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "relevant_lore": relevant,
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
            logger.exception("Error handling pruner request: %s", e)
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
    server = PrunerMCPServer()
    server.run_stdio()
