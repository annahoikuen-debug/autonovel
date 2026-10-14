"""Novel Formatter & Multi-Platform Linting MCP Server Implementation (Proposal 9)."""
from __future__ import annotations

from typing import Any, Dict
from src.mcp_servers.providers.formatter_provider import NovelFormatterProvider


class FormatterMCPServer:
    """Novel Formatter & Linting MCP Server 実装クラス"""

    def __init__(self, provider: NovelFormatterProvider | None = None) -> None:
        self.provider = provider or NovelFormatterProvider()

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC形式のリクエストを処理する"""
        method = request_data.get("method")
        params = request_data.get("params", {})
        req_id = request_data.get("id", 1)

        try:
            if method == "format_novel":
                text = params.get("text", "")
                platform = params.get("platform", "kakuyomu")
                options = params.get("options", {})
                res = self.provider.format_novel(text=text, platform=platform, options=options)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "formatted_text": res.formatted_text,
                        "original_length": res.original_length,
                        "formatted_length": res.formatted_length,
                        "platform": res.platform,
                        "is_valid": res.is_valid,
                        "issues": [
                            {
                                "issue_type": i.issue_type,
                                "message": i.message,
                                "severity": i.severity,
                                "line_number": i.line_number,
                                "snippet": i.snippet,
                                "suggested_fix": i.suggested_fix,
                            }
                            for i in res.issues
                        ],
                        "stats": res.stats,
                    },
                    "id": req_id,
                }

            elif method == "lint_novel":
                text = params.get("text", "")
                platform = params.get("platform", "kakuyomu")
                res = self.provider.lint_novel(text=text, platform=platform)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "platform": res.platform,
                        "is_valid": res.is_valid,
                        "issues": [
                            {
                                "issue_type": i.issue_type,
                                "message": i.message,
                                "severity": i.severity,
                                "line_number": i.line_number,
                                "snippet": i.snippet,
                                "suggested_fix": i.suggested_fix,
                            }
                            for i in res.issues
                        ],
                        "stats": res.stats,
                    },
                    "id": req_id,
                }

            elif method == "export_episode":
                title = params.get("title", "")
                content = params.get("content", "")
                platform = params.get("platform", "kakuyomu")
                foreword = params.get("foreword", "")
                afterword = params.get("afterword", "")
                res = self.provider.export_episode(
                    title=title,
                    content=content,
                    platform=platform,
                    foreword=foreword,
                    afterword=afterword,
                )
                return {
                    "jsonrpc": "2.0",
                    "result": res,
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
