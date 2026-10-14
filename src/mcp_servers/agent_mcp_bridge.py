"""MCP Agent Bridge - Connecting core agents (WritingAgent, AuditAgent) with local MCP servers/providers."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.mcp_servers.providers.lore_provider import LoreProvider
from src.mcp_servers.providers.vocab_provider import SensoryVocabProvider
from src.mcp_servers.providers.tension_provider import TensionAnalyzer
from src.mcp_servers.providers.audit_provider import AuditProvider
from src.mcp_servers.providers.formatter_provider import NovelFormatterProvider
from src.mcp_servers.providers.patch_provider import SurgicalPatchProvider
from src.mcp_servers.providers.pruning_provider import ContextPruningProvider
from src.mcp_servers.lore_server import LoreMCPServer
from src.mcp_servers.vocab_server import VocabMCPServer
from src.mcp_servers.tension_server import TensionMCPServer
from src.mcp_servers.audit_mcp_server import AuditMCPServer
from src.mcp_servers.formatter_server import FormatterMCPServer
from src.mcp_servers.patch_server import PatchMCPServer
from src.mcp_servers.pruner_server import PrunerMCPServer

logger = logging.getLogger(__name__)


class AgentMCPBridge:
    """エージェントと各MCPサーバー間を仲介し、オンデマンドのツール呼び出しを提供するブリッジ"""

    def __init__(
        self,
        lore_provider: Optional[LoreProvider] = None,
        vocab_provider: Optional[SensoryVocabProvider] = None,
        tension_analyzer: Optional[TensionAnalyzer] = None,
        audit_provider: Optional[AuditProvider] = None,
        formatter_provider: Optional[NovelFormatterProvider] = None,
        patch_provider: Optional[SurgicalPatchProvider] = None,
        pruning_provider: Optional[ContextPruningProvider] = None,
    ) -> None:
        self.lore_server = LoreMCPServer(lore_provider or LoreProvider())
        self.vocab_server = VocabMCPServer(vocab_provider or SensoryVocabProvider())
        self.tension_server = TensionMCPServer(tension_analyzer or TensionAnalyzer())
        self.audit_server = AuditMCPServer(audit_provider or AuditProvider())
        self.formatter_server = FormatterMCPServer(formatter_provider or NovelFormatterProvider())
        self.patch_server = PatchMCPServer(patch_provider or SurgicalPatchProvider())
        self.pruner_server = PrunerMCPServer(pruning_provider or ContextPruningProvider())

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

    def suggest_sensory_metaphors(
        self,
        keyword: str,
        genre: str = "general",
        intensity: Optional[float] = None,
    ) -> List[str]:
        """指定キーワードに対する五感・比喩表現を提案する"""
        params: Dict[str, Any] = {"keyword": keyword, "genre": genre}
        if intensity is not None:
            params["intensity"] = intensity
        req = {
            "jsonrpc": "2.0",
            "method": "suggest_metaphors",
            "params": params,
            "id": 2,
        }
        res = self.vocab_server.handle_request(req)
        return res.get("result", {}).get("suggestions", [])

    def suggest_metaphors(
        self,
        keyword: str,
        genre: str = "general",
        intensity: Optional[float] = None,
    ) -> List[str]:
        """suggest_sensory_metaphors のエイリアス"""
        return self.suggest_sensory_metaphors(keyword, genre, intensity)

    def sample_vocab_by_intensity(
        self,
        category: str = "all",
        intensity: float = 0.5,
        genre: str = "erotic",
        count: int = 4,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """指定の情動強度（0.0〜1.0）に応じた感覚・比喩・心理語彙を動的サンプリングする（トークン削減用）"""
        req = {
            "jsonrpc": "2.0",
            "method": "sample_by_intensity",
            "params": {
                "category": category,
                "intensity": intensity,
                "genre": genre,
                "count": count,
                "seed": seed,
            },
            "id": 11,
        }
        res = self.vocab_server.handle_request(req)
        return res.get("result", {})

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

    def generate_target_curve(self, curve_type: str = "climax_catharsis") -> Dict[str, Any]:
        """エピソードの目標感情曲線（テンション波形と各幕の指示）を生成する"""
        req = {
            "jsonrpc": "2.0",
            "method": "generate_target_curve",
            "params": {"curve_type": curve_type},
            "id": 14,
        }
        res = self.tension_server.handle_request(req)
        return res.get("result", {})

    def analyze_novel_arc(
        self,
        text: str,
        curve_type: str = "climax_catharsis",
        custom_targets: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """本文のセグメント別テンション推移を分析し、中だるみ・起伏不足と目標適合度を判定する"""
        params: Dict[str, Any] = {"text": text, "curve_type": curve_type}
        if custom_targets is not None:
            params["custom_targets"] = custom_targets
        req = {
            "jsonrpc": "2.0",
            "method": "analyze_novel_arc",
            "params": params,
            "id": 15,
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

    def pre_screen_for_auditor(
        self,
        text: str,
        specialist_name: Optional[str] = None,
        bypass_threshold: float = 90.0,
    ) -> Dict[str, Any]:
        """決定論的プレ・オーディットを実行し、LLM呼び出しスキップ可否・スコアを取得する"""
        req = {
            "jsonrpc": "2.0",
            "method": "pre_screen",
            "params": {
                "text": text,
                "specialist_name": specialist_name,
                "bypass_threshold": bypass_threshold,
            },
            "id": 5,
        }
        res = self.audit_server.handle_request(req)
        return res.get("result", {})

    def format_novel(
        self,
        text: str,
        platform: str = "kakuyomu",
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """指定プラットフォーム向けに小説本文を完全決定論的（0トークン）に整形する"""
        req = {
            "jsonrpc": "2.0",
            "method": "format_novel",
            "params": {
                "text": text,
                "platform": platform,
                "options": options or {},
            },
            "id": 6,
        }
        res = self.formatter_server.handle_request(req)
        return res.get("result", {})

    def lint_novel(
        self,
        text: str,
        platform: str = "kakuyomu",
    ) -> Dict[str, Any]:
        """小説本文の作法・体裁を決定論的にリント検証する"""
        req = {
            "jsonrpc": "2.0",
            "method": "lint_novel",
            "params": {
                "text": text,
                "platform": platform,
            },
            "id": 7,
        }
        res = self.formatter_server.handle_request(req)
        return res.get("result", {})

    def export_formatted_episode(
        self,
        title: str,
        content: str,
        platform: str = "kakuyomu",
        foreword: str = "",
        afterword: str = "",
    ) -> Dict[str, Any]:
        """前書き・後書き・タイトル制限を含めたエピソード完全パッケージングを取得する"""
        req = {
            "jsonrpc": "2.0",
            "method": "export_episode",
            "params": {
                "title": title,
                "content": content,
                "platform": platform,
                "foreword": foreword,
                "afterword": afterword,
            },
            "id": 8,
        }
        res = self.formatter_server.handle_request(req)
        return res.get("result", {})

    def apply_surgical_diffs(
        self,
        original_text: str,
        diffs: List[Any],
        allow_fuzzy: bool = True,
    ) -> Dict[str, Any]:
        """ActionableDiff を元に本文へ外科的ピンポイント置換を安全適用する（0トークン・差分修正）"""
        req = {
            "jsonrpc": "2.0",
            "method": "apply_actionable_diffs",
            "params": {
                "original_text": original_text,
                "diffs": diffs,
                "allow_fuzzy": allow_fuzzy,
            },
            "id": 9,
        }
        res = self.patch_server.handle_request(req)
        return res.get("result", {})

    def extract_patch_windows(
        self,
        original_text: str,
        target_quotes: List[str],
        padding_lines: int = 2,
    ) -> Dict[str, Any]:
        """局所修正用のコンテキストウィンドウを切り出す（LLMトークン削減用）"""
        req = {
            "jsonrpc": "2.0",
            "method": "extract_patch_windows",
            "params": {
                "original_text": original_text,
                "target_quotes": target_quotes,
                "padding_lines": padding_lines,
            },
            "id": 10,
        }
        res = self.patch_server.handle_request(req)
        return res.get("result", {})

    def prune_context(
        self,
        plot_blueprint: str,
        characters: Optional[List[Dict[str, Any]]] = None,
        world_lore: Optional[List[Dict[str, Any]]] = None,
        foreshadowings: Optional[List[Dict[str, Any]]] = None,
        target_token_budget: int = 2000,
        current_episode: Optional[int] = None,
        pov_character: Optional[str] = None,
    ) -> Dict[str, Any]:
        """エピソードのプロットに合わせてキャラ設定・世界観・伏線を動的プルーニング（30%〜70%トークン削減）"""
        req = {
            "jsonrpc": "2.0",
            "method": "prune_context",
            "params": {
                "plot_blueprint": plot_blueprint,
                "characters": characters or [],
                "world_lore": world_lore or [],
                "foreshadowings": foreshadowings or [],
                "target_token_budget": target_token_budget,
                "current_episode": current_episode,
                "pov_character": pov_character,
            },
            "id": 11,
        }
        res = self.pruner_server.handle_request(req)
        return res.get("result", {})

    def prune_characters(
        self,
        plot_blueprint: str,
        characters: List[Dict[str, Any]],
        pov_character: Optional[str] = None,
    ) -> Dict[str, Any]:
        """プロット本文に出現するキャラのみを抽出・仕分けする"""
        req = {
            "jsonrpc": "2.0",
            "method": "prune_characters",
            "params": {
                "plot_blueprint": plot_blueprint,
                "characters": characters,
                "pov_character": pov_character,
            },
            "id": 12,
        }
        res = self.pruner_server.handle_request(req)
        return res.get("result", {})

    def prune_lore(
        self,
        plot_blueprint: str,
        world_lore: List[Dict[str, Any]],
        active_character_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """プロットに関連する世界観設定のみをスコアリング抽出する"""
        req = {
            "jsonrpc": "2.0",
            "method": "prune_lore",
            "params": {
                "plot_blueprint": plot_blueprint,
                "world_lore": world_lore,
                "active_character_names": active_character_names or [],
            },
            "id": 13,
        }
        res = self.pruner_server.handle_request(req)
        return res.get("result", {})
