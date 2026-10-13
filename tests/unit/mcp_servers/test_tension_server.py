"""Unit tests for TensionMCPServer."""
from __future__ import annotations

from src.mcp_servers.providers.tension_provider import TensionAnalyzer
from src.mcp_servers.tension_server import TensionMCPServer


def test_tension_mcp_server_json_rpc():
    analyzer = TensionAnalyzer()
    server = TensionMCPServer(analyzer)

    # Valid check_emotional_tension call
    req = {
        "jsonrpc": "2.0",
        "method": "check_emotional_tension",
        "params": {
            "text": "激しい戦いが始まった！ 剣が交錯する！",
            "target_tension": 50.0,
        },
        "id": 1,
    }
    resp = server.handle_request(req)
    assert resp["result"]["tension_score"] > 0.0
    assert resp["result"]["dominant_emotion"] == "tension"

    # Unknown method
    unk_req = {"jsonrpc": "2.0", "method": "unknown", "id": 2}
    resp2 = server.handle_request(unk_req)
    assert "error" in resp2

    # Error handling
    err_req = {"jsonrpc": "2.0", "method": "check_emotional_tension", "params": None, "id": 3}
    resp3 = server.handle_request(err_req)
    assert "error" in resp3
