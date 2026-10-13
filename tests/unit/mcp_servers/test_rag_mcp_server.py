"""Unit tests for RAG & Memory MCP Server."""
from __future__ import annotations

from src.mcp_servers.providers.rag_provider import RAGMemoryProvider, RAGQueryRequest
from src.mcp_servers.rag_mcp_server import RAGMCPServer


def test_rag_provider_add_and_query():
    provider = RAGMemoryProvider()
    provider.add_document("The hero entered the dark dungeon.", {"chapter": 1})
    provider.add_document("The dragon slept deeply in the cavern.", {"chapter": 2})

    req = RAGQueryRequest(query="hero dungeon", top_k=2)
    res = provider.query(req)
    assert len(res.results) >= 1
    assert "dungeon" in res.results[0].content


def test_rag_mcp_server_json_rpc():
    provider = RAGMemoryProvider()
    server = RAGMCPServer(provider)

    # Add document via JSON-RPC
    add_req = {
        "jsonrpc": "2.0",
        "method": "add_document",
        "params": {
            "content": "Ancient sword gleamed in moonlight.",
            "metadata": {"item": "sword"},
        },
        "id": 1,
    }
    resp = server.handle_request(add_req)
    assert resp["result"]["status"] == "success"

    # Query via JSON-RPC
    query_req = {
        "jsonrpc": "2.0",
        "method": "query_rag",
        "params": {
            "query": "Ancient sword",
            "top_k": 1,
        },
        "id": 2,
    }
    resp2 = server.handle_request(query_req)
    assert len(resp2["result"]["results"]) == 1
    assert "sword" in resp2["result"]["results"][0]["content"]

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
        "method": "add_document",
        "params": None,
        "id": 4,
    }
    resp4 = server.handle_request(err_req)
    assert "error" in resp4
    assert resp4["error"]["code"] == -32603
