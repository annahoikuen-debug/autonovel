"""Compliance & Audit MCP Server Implementation."""
from __future__ import annotations

from typing import Any, Dict
from src.mcp_servers.providers.audit_provider import (
    AuditProvider,
    AuditRule,
    AuditRequest,
)


class AuditMCPServer:
    """Compliance & Audit MCP Server 簡易実装クラス"""

    def __init__(self, provider: AuditProvider) -> None:
        self.provider = provider

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC形式のリクエストを処理する"""
        method = request_data.get("method")
        params = request_data.get("params", {})
        req_id = request_data.get("id", 1)

        try:
            if method == "register_rule":
                rule = AuditRule(**params)
                self.provider.register_rule(rule)
                return {"jsonrpc": "2.0", "result": {"status": "success"}, "id": req_id}

            elif method == "audit_text":
                req = AuditRequest(
                    text=params.get("text", ""),
                    active_rules=params.get("active_rules", []),
                )
                res = self.provider.audit(req)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "is_compliant": res.is_compliant,
                        "violations": [
                            {
                                "rule_id": v.rule_id,
                                "message": v.message,
                                "severity": v.severity,
                            }
                            for v in res.violations
                        ],
                        "score": res.score,
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
