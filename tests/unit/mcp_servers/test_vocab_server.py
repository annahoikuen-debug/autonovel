"""Unit tests for VocabMCPServer."""
from __future__ import annotations

from src.mcp_servers.providers.vocab_provider import SensoryVocabProvider
from src.mcp_servers.vocab_server import VocabMCPServer


def test_vocab_mcp_server_json_rpc():
    provider = SensoryVocabProvider(auto_load_defaults=False)
    server = VocabMCPServer(provider)

    # 1. Register words via JSON-RPC
    reg_req = {
        "jsonrpc": "2.0",
        "method": "register_words",
        "params": {
            "genre": "mystery",
            "words": [
                {
                    "word": "時計の秒針の音",
                    "category": "auditory",
                    "example_sentence": "静寂の中に秒針の音が響く。",
                    "nuance": "suspense"
                }
            ]
        },
        "id": 1,
    }
    resp1 = server.handle_request(reg_req)
    assert resp1["result"]["status"] == "success"

    # 2. Suggest metaphors via JSON-RPC
    sug_req = {
        "jsonrpc": "2.0",
        "method": "suggest_metaphors",
        "params": {"keyword": "秒針", "genre": "mystery"},
        "id": 2,
    }
    resp2 = server.handle_request(sug_req)
    assert len(resp2["result"]["suggestions"]) == 1

    # 3. Resources list
    list_req = {"jsonrpc": "2.0", "method": "resources/list", "id": 3}
    resp3 = server.handle_request(list_req)
    assert len(resp3["result"]["resources"]) == 1

    # 4. Resources read
    read_req = {
        "jsonrpc": "2.0",
        "method": "resources/read",
        "params": {"uri": "novel://vocab/sensory/mystery"},
        "id": 4,
    }
    resp4 = server.handle_request(read_req)
    assert "秒針の音" in resp4["result"]["contents"][0]["text"]

    # 5. Unknown method
    unk_req = {"jsonrpc": "2.0", "method": "unknown", "id": 5}
    resp5 = server.handle_request(unk_req)
    assert "error" in resp5

    # 6. Error handling
    err_req = {"jsonrpc": "2.0", "method": "register_words", "params": None, "id": 6}
    resp6 = server.handle_request(err_req)
    assert "error" in resp6
