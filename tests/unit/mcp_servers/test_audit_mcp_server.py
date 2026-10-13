"""Unit tests for Compliance & Audit MCP Server."""
from __future__ import annotations

from src.mcp_servers.providers.audit_provider import AuditProvider, AuditRule, AuditRequest
from src.mcp_servers.audit_mcp_server import AuditMCPServer


def test_audit_provider_rules():
    provider = AuditProvider()
    provider.register_rule(AuditRule(rule_id="no_forbidden_words", description="No NGWORD", severity="error"))
    provider.register_rule(AuditRule(rule_id="min_length", description="Length >= 10", severity="warning"))

    # Pass case
    req = AuditRequest(text="This is a valid long text.", active_rules=["no_forbidden_words", "min_length"])
    res = provider.audit(req)
    assert res.is_compliant is True
    assert res.score == 100.0

    # Violation case
    req2 = AuditRequest(text="NGWORD", active_rules=["no_forbidden_words", "min_length"])
    res2 = provider.audit(req2)
    assert res2.is_compliant is False
    assert len(res2.violations) == 2




def test_audit_mcp_server_json_rpc():
    provider = AuditProvider()
    server = AuditMCPServer(provider)

    # Register rule via JSON-RPC
    reg_req = {
        "jsonrpc": "2.0",
        "method": "register_rule",
        "params": {
            "rule_id": "no_forbidden_words",
            "description": "Check forbidden words",
            "severity": "error",
        },
        "id": 1,
    }
    resp = server.handle_request(reg_req)
    assert resp["result"]["status"] == "success"

    # Audit via JSON-RPC
    audit_req = {
        "jsonrpc": "2.0",
        "method": "audit_text",
        "params": {
            "text": "contains NGWORD here",
            "active_rules": ["no_forbidden_words"],
        },
        "id": 2,
    }
    resp2 = server.handle_request(audit_req)
    assert resp2["result"]["is_compliant"] is False
    assert len(resp2["result"]["violations"]) == 1

    # Unknown method
    unknown_req = {
        "jsonrpc": "2.0",
        "method": "unknown",
        "params": {},
        "id": 3,
    }
    resp3 = server.handle_request(unknown_req)
    assert "error" in resp3
    assert resp3["error"]["code"] == -32601

    # Error handling
    err_req = {
        "jsonrpc": "2.0",
        "method": "register_rule",
        "params": None,
        "id": 4,
    }
    resp4 = server.handle_request(err_req)
    assert "error" in resp4
    assert resp4["error"]["code"] == -32603
