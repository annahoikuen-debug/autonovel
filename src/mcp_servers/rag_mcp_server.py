"""RAG & Memory MCP Server Implementation."""

from __future__ import annotations

from typing import Any, Dict
from src.mcp_servers.providers.rag_provider import (
    RAGMemoryProvider,
    RAGQueryRequest,
)


class RAGMCPServer:
    """RAG & Memory MCP Server 簡易実装クラス"""

    def __init__(self, provider: RAGMemoryProvider) -> None:
        self.provider = provider

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC形式のリクエストを処理する"""
        method = request_data.get("method")
        params = request_data.get("params", {})
        req_id = request_data.get("id", 1)

        try:
            if method == "add_document":
                content = params.get("content", "")
                metadata = params.get("metadata", {})
                self.provider.add_document(content, metadata)
                return {"jsonrpc": "2.0", "result": {"status": "success"}, "id": req_id}

            elif method == "query_rag":
                req = RAGQueryRequest(
                    query=params.get("query", ""),
                    top_k=params.get("top_k", 5),
                    filters=params.get("filters", {}),
                )
                res = self.provider.query(req)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "results": [
                            {
                                "content": r.content,
                                "score": r.score,
                                "metadata": r.metadata,
                            }
                            for r in res.results
                        ],
                        "summary": res.summary,
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
