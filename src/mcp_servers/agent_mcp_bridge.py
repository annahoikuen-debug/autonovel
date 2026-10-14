"""MCP Agent Bridge - Connecting core agents (WritingAgent, AuditAgent) with deterministic tool providers."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.mcp_servers.providers.lore_provider import LoreProvider
from src.mcp_servers.providers.vocab_provider import SensoryVocabProvider
from src.mcp_servers.providers.tension_provider import TensionAnalyzer
from src.mcp_servers.providers.audit_provider import AuditProvider, AuditRequest
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
from src.mcp_servers.pruning_schemas import PruneContextRequest
from src.mcp_servers.schemas import LoreQueryRequest

logger = logging.getLogger(__name__)

# プロセス内共有シングルトンインスタンス（毎呼び出しの辞書全再構築を防止）
_DEFAULT_BRIDGE: Optional[AgentMCPBridge] = None


def get_default_bridge() -> AgentMCPBridge:
    """共有シングルトン AgentMCPBridge インスタンスを取得する（辞書再構築コストをゼロ化）"""
    global _DEFAULT_BRIDGE
    if _DEFAULT_BRIDGE is None:
        _DEFAULT_BRIDGE = AgentMCPBridge()
    return _DEFAULT_BRIDGE


def reset_default_bridge() -> None:
    """テスト時などに共有シングルトンをリセットする"""
    global _DEFAULT_BRIDGE
    _DEFAULT_BRIDGE = None


class AgentMCPBridge:
    """エージェントと各決定論的ツールプロバイダー間を仲介し、高速・型安全な直接呼び出しを提供するブリッジ"""

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
        # プロバイダー層の保持（内部実行の Fast-Path 用）
        self.lore_provider = lore_provider or LoreProvider()
        self.vocab_provider = vocab_provider or SensoryVocabProvider()
        self.tension_analyzer = tension_analyzer or TensionAnalyzer()
        self.audit_provider = audit_provider or AuditProvider()
        self.formatter_provider = formatter_provider or NovelFormatterProvider()
        self.patch_provider = patch_provider or SurgicalPatchProvider()
        self.pruning_provider = pruning_provider or ContextPruningProvider()

        # JSON-RPC サーバー層の保持（下位互換性および外部MCPクライアント接続用）
        self.lore_server = LoreMCPServer(self.lore_provider)
        self.vocab_server = VocabMCPServer(self.vocab_provider)
        self.tension_server = TensionMCPServer(self.tension_analyzer)
        self.audit_server = AuditMCPServer(self.audit_provider)
        self.formatter_server = FormatterMCPServer(self.formatter_provider)
        self.patch_server = PatchMCPServer(self.patch_provider)
        self.pruner_server = PrunerMCPServer(self.pruning_provider)

    # ── 1. Lore / 世界観 ──────────────────────────────────────────

    def get_lore_context(
        self,
        query: str,
        character_names: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Lore（世界観・キャラクター）情報をオンデマンドで取得する（直接Fast-Path）"""
        req = LoreQueryRequest(
            query=query,
            character_names=character_names or [],
            tags=tags or [],
        )
        res = self.lore_provider.query(req)
        return {
            "characters": [vars(c) for c in res.characters],
            "bible_sections": [vars(s) for s in res.bible_sections],
            "compressed_summary": res.compressed_summary,
        }

    # ── 2. 語彙・感覚比喩サンプリング (提案4) ───────────────────────

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
        """指定の情動強度（0.0〜1.0）に応じた感覚・比喩・心理語彙を動的サンプリングする（直接Fast-Path）"""
        res = self.vocab_provider.sample_by_intensity(
            category=category,
            intensity=intensity,
            genre=genre,
            count=count,
            seed=seed,
        )
        return {
            "category": res.category,
            "target_intensity": res.target_intensity,
            "items": res.items,
            "count": res.count,
            "genre": res.genre,
        }

    # ── 3. テンション・感情曲線制御 (提案7) ────────────────────────

    def measure_tension(self, text: str, target_tension: Optional[float] = None) -> Dict[str, Any]:
        """テキストの緊張度・感情極性を計測する（直接Fast-Path）"""
        res = self.tension_analyzer.calculate_tension(text, target_tension=target_tension)
        return res.model_dump()

    def generate_target_curve(self, curve_type: str = "climax_catharsis") -> Dict[str, Any]:
        """エピソードの目標感情曲線（テンション波形と各幕の指示）を生成する（直接Fast-Path）"""
        res = self.tension_analyzer.generate_target_curve(curve_type=curve_type)
        return res.model_dump()

    def analyze_novel_arc(
        self,
        text: str,
        curve_type: str = "climax_catharsis",
        custom_targets: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """本文のセグメント別テンション推移を分析し、中だるみ・起伏不足と目標適合度を判定する（直接Fast-Path）"""
        res = self.tension_analyzer.analyze_novel_arc(
            text=text,
            curve_type=curve_type,
            custom_targets=custom_targets,
        )
        return res.model_dump()

    # ── 4. 決定論的プレ・オーディット (提案2) ───────────────────────

    def audit_static_rules(self, text: str, active_rules: Optional[List[str]] = None) -> Dict[str, Any]:
        """ローカル静的ルール・文体解析による監査を実行する（直接Fast-Path）"""
        req = AuditRequest(text=text, active_rules=active_rules or [])
        res = self.audit_provider.audit(req)
        return {
            "is_compliant": res.is_compliant,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "message": v.message,
                    "severity": v.severity,
                    "line_number": v.line_number,
                    "snippet": v.snippet,
                    "suggestion": v.suggestion,
                }
                for v in res.violations
            ],
            "score": res.score,
        }

    def pre_screen_for_auditor(
        self,
        text: str,
        specialist_name: Optional[str] = None,
        bypass_threshold: float = 90.0,
    ) -> Dict[str, Any]:
        """決定論的プレ・オーディットを実行し、LLM呼び出しスキップ可否・スコアを取得する（直接Fast-Path）"""
        res = self.audit_provider.pre_screen(
            text=text,
            specialist_name=specialist_name,
            bypass_threshold=bypass_threshold,
        )
        return {
            "passed": res.passed,
            "score": res.score,
            "bypass_eligible": res.bypass_eligible,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "message": v.message,
                    "severity": v.severity,
                    "line_number": v.line_number,
                    "snippet": v.snippet,
                    "suggestion": v.suggestion,
                }
                for v in res.violations
            ],
            "total_violations": len(res.violations),
            "details": res.details,
        }

    # ── 5. マルチプラットフォーム整形・リンター (提案9) ──────────────

    def format_novel(
        self,
        text: str,
        platform: str = "general",
        indent_style: str = "zenkaku",
        auto_ruby: bool = True,
    ) -> Dict[str, Any]:
        """指定投稿サイト（kakuyomu, narou, alphapolis等）向けに原稿を正規化・ルビ変換する（直接Fast-Path）"""
        res = self.formatter_provider.format_novel(
            text=text,
            platform=platform,
            options={"indent_style": indent_style, "auto_ruby": auto_ruby},
        )
        return {
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
        }

    def lint_novel(self, text: str, platform: str = "general") -> Dict[str, Any]:
        """投稿作法・禁止表現・三点リーダー・会話文末などの違反を高速チェックする（直接Fast-Path）"""
        res = self.formatter_provider.lint_novel(text=text, platform=platform)
        return {
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
        }

    def export_formatted_episode(
        self,
        title: str,
        content: str,
        platform: str = "kakuyomu",
        foreword: str = "",
        afterword: str = "",
    ) -> Dict[str, Any]:
        """前書き・後書き・タイトル制限を含めたエピソード完全パッケージングを取得する（直接Fast-Path）"""
        pkg = self.formatter_provider.export_episode(
            title=title,
            content=content,
            platform=platform,
            foreword=foreword,
            afterword=afterword,
        )
        return {
            "title": pkg.title,
            "body": pkg.body,
            "foreword": pkg.foreword,
            "afterword": pkg.afterword,
            "platform": pkg.platform,
            "full_export_text": pkg.full_export_text,
            "metadata": pkg.metadata,
        }

    # ── 6. 局所パッチ置換 (提案3) ──────────────────────────────────

    def apply_surgical_diffs(
        self,
        original_text: str,
        diffs: List[Any],
        allow_fuzzy: bool = True,
    ) -> Dict[str, Any]:
        """ActionableDiff を元に本文へ外科的ピンポイント置換を安全適用する（直接Fast-Path）"""
        res = self.patch_provider.apply_actionable_diffs(
            original_text=original_text,
            diffs=diffs,
            allow_fuzzy=allow_fuzzy,
        )
        return {
            "patched_text": res.patched_text,
            "original_text": res.original_text,
            "total_requested": res.total_requested,
            "applied_count": res.applied_count,
            "failed_count": res.failed_count,
            "applied_diffs": res.applied_diffs,
            "failed_diffs": res.failed_diffs,
            "is_fully_applied": res.is_fully_applied,
            "token_savings_estimate": res.token_savings_estimate,
        }

    def extract_patch_windows(
        self,
        original_text: str,
        target_quotes: List[str],
        padding_lines: int = 2,
    ) -> Dict[str, Any]:
        """局所修正用のコンテキストウィンドウを切り出す（直接Fast-Path）"""
        windows = self.patch_provider.extract_patch_windows(
            original_text=original_text,
            target_quotes=target_quotes,
            padding_lines=padding_lines,
        )
        return {
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
        }

    # ── 7. 動的コンテキスト・プルーニング (提案1) ────────────────────

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
        """エピソードのプロットに合わせてキャラ設定・世界観・伏線を動的プルーニング（直接Fast-Path）"""
        req = PruneContextRequest(
            plot_blueprint=plot_blueprint,
            characters=characters or [],
            world_lore=world_lore or [],
            foreshadowings=foreshadowings or [],
            target_token_budget=target_token_budget,
            current_episode=current_episode,
            pov_character=pov_character,
        )
        res = self.pruning_provider.prune_context(req)
        return res.model_dump()

    def prune_characters(
        self,
        plot_blueprint: str,
        characters: List[Dict[str, Any]],
        pov_character: Optional[str] = None,
    ) -> Dict[str, Any]:
        """プロット本文に出現するキャラのみを抽出・仕分けする（直接Fast-Path）"""
        active, peripheral, excluded = self.pruning_provider._filter_characters(
            characters=characters,
            plot=plot_blueprint,
            pov_character=pov_character,
        )
        return {
            "active_characters": active,
            "peripheral_characters": peripheral,
            "excluded_characters": excluded,
        }

    def prune_lore(
        self,
        plot_blueprint: str,
        world_lore: List[Dict[str, Any]],
        active_character_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """プロットに関連する世界観設定のみをスコアリング抽出する（直接Fast-Path）"""
        relevant = self.pruning_provider._filter_lore(
            world_lore=world_lore,
            plot=plot_blueprint,
            active_character_names=set(active_character_names or []),
        )
        return {
            "relevant_lore": relevant,
        }
