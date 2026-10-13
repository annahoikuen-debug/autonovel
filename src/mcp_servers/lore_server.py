"""Lore/Bible MCP Server Implementation (JSON-RPC / Tool Provider)."""
from __future__ import annotations

import json
import sys
from typing import Any, Dict
from src.mcp_servers.providers.lore_provider import LoreProvider
from src.mcp_servers.schemas import CharacterProfile, WorldBibleSection, LoreQueryRequest


class LoreMCPServer:
    """Lore/Bible MCP Server 簡易実装クラス"""

    def __init__(self, provider: LoreProvider) -> None:
        self.provider = provider

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC形式のリクエストを処理する"""
        method = request_data.get("method")
        params = request_data.get("params", {})
        req_id = request_data.get("id", 1)

        try:
            if method == "register_character":
                profile = CharacterProfile(**params)
                self.provider.register_character(profile)
                return {"jsonrpc": "2.0", "result": {"status": "success"}, "id": req_id}

            elif method == "register_bible_section":
                section = WorldBibleSection(**params)
                self.provider.register_bible_section(section)
                return {"jsonrpc": "2.0", "result": {"status": "success"}, "id": req_id}

            elif method == "query_lore":
                req = LoreQueryRequest(**params)
                res = self.provider.query(req)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "characters": [vars(c) for c in res.characters],
                        "bible_sections": [vars(s) for s in res.bible_sections],
                        "compressed_summary": res.compressed_summary,
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
