"""Unit tests for TransitionMCPServer."""

from __future__ import annotations

from src.mcp_servers.providers.transition_provider import SceneTransitionValidator
from src.mcp_servers.transition_server import TransitionMCPServer


def test_transition_mcp_server_json_rpc():
    validator = SceneTransitionValidator()
    server = TransitionMCPServer(validator)

    # Valid transition call
    req = {
        "jsonrpc": "2.0",
        "method": "validate_scene_transition",
        "params": {
            "from_state": {"character_name": "Alice", "location": "Forest"},
            "to_state": {"character_name": "Alice", "location": "Forest"},
        },
        "id": 1,
    }
    resp = server.handle_request(req)
    assert resp["result"]["is_valid"] is True

    # Invalid transition call (Dungeon -> Castle)
    req2 = {
        "jsonrpc": "2.0",
        "method": "validate_scene_transition",
        "params": {
            "from_state": {"character_name": "Alice", "location": "Dungeon"},
            "to_state": {"character_name": "Alice", "location": "Royal Castle"},
        },
        "id": 2,
    }
    resp2 = server.handle_request(req2)
    assert resp2["result"]["is_valid"] is False
    assert len(resp2["result"]["conflicts"]) > 0

    # Unknown method
    unk_req = {"jsonrpc": "2.0", "method": "unknown", "id": 3}
    resp3 = server.handle_request(unk_req)
    assert "error" in resp3

    # Error handling
    err_req = {"jsonrpc": "2.0", "method": "validate_scene_transition", "params": None, "id": 4}
    resp4 = server.handle_request(err_req)
    assert "error" in resp4
