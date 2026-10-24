"""Unit tests for TimelineMCPServer."""

from __future__ import annotations

from src.mcp_servers.providers.timeline_provider import TimelineResourceProvider
from src.mcp_servers.timeline_server import TimelineMCPServer


def test_timeline_mcp_server_json_rpc():
    provider = TimelineResourceProvider()
    server = TimelineMCPServer(provider)

    # 1. Add event via JSON-RPC
    add_ev_req = {
        "jsonrpc": "2.0",
        "method": "add_timeline_event",
        "params": {"timestamp": "Year 100", "location": "Capital", "description": "Coronation", "characters": ["King"]},
        "id": 1,
    }
    resp1 = server.handle_request(add_ev_req)
    assert resp1["result"]["status"] == "success"

    # 2. Record digest via JSON-RPC
    rec_dig_req = {
        "jsonrpc": "2.0",
        "method": "record_episode_digest",
        "params": {"episode_num": 10, "summary": "King was crowned.", "footholds_or_foreshadowings": ["Dark prophecy"]},
        "id": 2,
    }
    resp2 = server.handle_request(rec_dig_req)
    assert resp2["result"]["status"] == "success"

    # 3. Resources list
    list_req = {
        "jsonrpc": "2.0",
        "method": "resources/list",
        "id": 3,
    }
    resp3 = server.handle_request(list_req)
    resources = resp3["result"]["resources"]
    assert len(resources) == 2  # timeline + episode 10 digest

    # 4. Resources read (timeline)
    read_tl_req = {
        "jsonrpc": "2.0",
        "method": "resources/read",
        "params": {"uri": "novel://memory/timeline"},
        "id": 4,
    }
    resp4 = server.handle_request(read_tl_req)
    assert "Coronation" in resp4["result"]["contents"][0]["text"]

    # 5. Resources read (digest)
    read_dig_req = {
        "jsonrpc": "2.0",
        "method": "resources/read",
        "params": {"uri": "novel://memory/episode/10/digest"},
        "id": 5,
    }
    resp5 = server.handle_request(read_dig_req)
    assert "King was crowned." in resp5["result"]["contents"][0]["text"]

    # 6. Unknown method
    unk_req = {"jsonrpc": "2.0", "method": "unknown", "id": 6}
    resp6 = server.handle_request(unk_req)
    assert "error" in resp6

    # 7. Error handling
    err_req = {"jsonrpc": "2.0", "method": "add_timeline_event", "params": None, "id": 7}
    resp7 = server.handle_request(err_req)
    assert "error" in resp7
