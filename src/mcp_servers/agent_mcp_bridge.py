"""MCP Agent Bridge - Connecting core agents (WritingAgent, AuditAgent) with local MCP servers/providers."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.mcp_servers.providers.lore_provider import LoreProvider
from src.mcp_servers.providers.vocab_provider import SensoryVocabProvider
from src.mcp_servers.providers.tension_provider import TensionAnalyzer
from src.mcp_servers.providers.audit_provider import AuditProvider
from src.mcp_servers.lore_server import LoreMCPServer
from src.mcp_servers.vocab_server import VocabMCPServer
from src.mcp_servers.tension_server import TensionMCPServer
from src.mcp_servers.audit_mcp_server import AuditMCPServer

logger = logging.getLogger(__name__)


class AgentMCPBridge:
    """エージェントと各MCPサーバー間を仲介し、オンデマンドのツール呼び出しを提供するブリッジ"""

    def __init__(
        self,
        lore_provider: Optional[LoreProvider] = None,
        vocab_provider: Optional[SensoryVocabProvider] = None,
        tension_analyzer: Optional[TensionAnalyzer] = None,
        audit_provider: Optional[AuditProvider] = None,
    ) -> None:
        self.lore_server = LoreMCPServer(lore_provider or LoreProvider())
        self.vocab_server = VocabMCPServer(vocab_provider or SensoryVocabProvider())
        self.tension_server = TensionMCPServer(tension_analyzer or TensionAnalyzer())
        self.audit_server = AuditMCPServer(audit_provider or AuditProvider())

    def get_lore_context(self, query: str, character_names: Optional[List[str]] = None, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Lore（世界観・キャラクター）情報をオンデマンドで取得する"""
        req = {
            "jsonrpc": "2.0",
            "method": "query_lore",
            "params": {
                "query": query,
                "character_names": character_names or [],
                "tags": tags or [],
            },
            "id": 1,
        }
        res = self.lore_server.handle_request(req)
        return res.get("result", {})

    def suggest_sensory_metaphors(self, keyword: str, genre: str = "general") -> List[str]:
        """指定キーワードに対する五感・比喩表現を提案する"""
        req = {
            "jsonrpc": "2.0",
            "method": "suggest_metaphors",
            "params": {"keyword": keyword, "genre": genre},
            "id": 2,
        }
        res = self.vocab_server.handle_request(req)
        return res.get("result", {}).get("suggestions", [])

    def suggest_metaphors(self, keyword: str, genre: str = "general") -> List[str]:
        """suggest_sensory_metaphors のエイリアス"""
        return self.suggest_sensory_metaphors(keyword, genre)

    def measure_tension(self, text: str, target_tension: Optional[float] = None) -> Dict[str, Any]:
        """テキストの緊張度・感情極性を計測する"""
        params: Dict[str, Any] = {"text": text}
        if target_tension is not None:
            params["target_tension"] = target_tension
        req = {
            "jsonrpc": "2.0",
            "method": "check_emotional_tension",
            "params": params,
            "id": 3,
        }
        res = self.tension_server.handle_request(req)
        return res.get("result", {})

    def audit_static_rules(self, text: str, active_rules: Optional[List[str]] = None) -> Dict[str, Any]:
        """ローカル静的ルール・文体解析による監査を実行する"""
        req = {
            "jsonrpc": "2.0",
            "method": "audit_text",
            "params": {
                "text": text,
                "active_rules": active_rules or [],
            },
            "id": 4,
        }
        res = self.audit_server.handle_request(req)
        return res.get("result", {})
