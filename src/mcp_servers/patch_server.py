"""Surgical Patch MCP Server Implementation (Proposal 3)."""
from __future__ import annotations

from typing import Any, Dict
from src.mcp_servers.providers.patch_provider import SurgicalPatchProvider


class PatchMCPServer:
    """Surgical Patch MCP Server 実装クラス"""

    def __init__(self, provider: SurgicalPatchProvider | None = None) -> None:
        self.provider = provider or SurgicalPatchProvider()

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC形式のリクエストを処理する"""
        method = request_data.get("method")
        params = request_data.get("params", {})
        req_id = request_data.get("id", 1)

        try:
            if method == "apply_actionable_diffs":
                original_text = params.get("original_text", "")
                diffs = params.get("diffs", [])
                allow_fuzzy = params.get("allow_fuzzy", True)

                res = self.provider.apply_actionable_diffs(
                    original_text=original_text,
                    diffs=diffs,
                    allow_fuzzy=allow_fuzzy,
                )
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "patched_text": res.patched_text,
                        "total_requested": res.total_requested,
                        "applied_count": res.applied_count,
                        "failed_count": res.failed_count,
                        "applied_diffs": res.applied_diffs,
                        "failed_diffs": res.failed_diffs,
                        "is_fully_applied": res.is_fully_applied,
                        "token_savings_estimate": res.token_savings_estimate,
                    },
                    "id": req_id,
                }

            elif method == "extract_patch_windows":
                original_text = params.get("original_text", "")
                target_quotes = params.get("target_quotes", [])
                padding_lines = params.get("padding_lines", 2)

                windows = self.provider.extract_patch_windows(
                    original_text=original_text,
                    target_quotes=target_quotes,
                    padding_lines=padding_lines,
                )
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "windows": [
                            {
                                "window_id": w.window_id,
                                "target_quote": w.target_quote,
                                "padded_context": w.padded_context,
                                "start_char_idx": w.start_char_idx,
                                "end_char_idx": w.end_char_idx,
                                "location_desc": w.location_desc,
                            }
                            for w in windows
                        ],
                        "total_windows": len(windows),
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
