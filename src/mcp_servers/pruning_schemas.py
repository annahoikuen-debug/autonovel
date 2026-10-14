"""Data schemas for Context Pruning MCP Server (Dynamic Context Pruning)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CharacterProfileItem(BaseModel):
    """キャラクタープロファイル定義"""
    name: str
    aliases: List[str] = Field(default_factory=list)
    role: str = ""
    personality: str = ""
    speech_pattern: str = ""
    secrets_and_flaws: str = ""
    relationships: Dict[str, str] = Field(default_factory=dict)
    importance: str = "main"  # main, sub, mob
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LoreItem(BaseModel):
    """世界観・Lore設定項目"""
    id: str
    title: str
    category: str = "world"  # world, magic, geography, faction, item
    content: str = ""
    keywords: List[str] = Field(default_factory=list)
    importance: int = 1  # 1 (low) to 5 (critical)


class ForeshadowingItem(BaseModel):
    """伏線項目"""
    id: str
    title: str
    description: str = ""
    target_episode: Optional[int] = None
    planted_episode: Optional[int] = None
    status: str = "unresolved"  # planted, pending, unresolved, resolved
    priority: int = 1


class PruneContextRequest(BaseModel):
    """コンテキスト枝刈り（プルーニング）リクエスト"""
    plot_blueprint: str = Field(..., description="エピソードプロット・シーン概要・あらすじ本文")
    characters: List[Dict[str, Any]] = Field(default_factory=list, description="全キャラクター定義リスト")
    world_lore: List[Dict[str, Any]] = Field(default_factory=list, description="世界観設定項目リスト")
    foreshadowings: List[Dict[str, Any]] = Field(default_factory=list, description="伏線リスト")
    target_token_budget: int = Field(default=2000, description="プルーニング後の目標最大トークン数")
    current_episode: Optional[int] = Field(default=None, description="対象エピソード番号")
    pov_character: Optional[str] = Field(default=None, description="視点キャラクター名（強制保持）")


class PrunedContextResult(BaseModel):
    """プルーニング結果"""
    active_characters: List[Dict[str, Any]] = Field(default_factory=list, description="登場キャラ（詳細保持）")
    peripheral_characters: List[Dict[str, Any]] = Field(default_factory=list, description="関係キャラ（1行サマリ）")
    excluded_characters: List[str] = Field(default_factory=list, description="完全除外されたキャラ名")
    relevant_lore: List[Dict[str, Any]] = Field(default_factory=list, description="関連世界観項目")
    prioritized_foreshadowings: List[Dict[str, Any]] = Field(default_factory=list, description="優先伏線")
    formatted_prompt_context: str = Field(default="", description="プロンプト注入用の整形済みテキスト")
    original_token_estimate: int = Field(default=0, description="プルーニング前推定トークン数")
    pruned_token_estimate: int = Field(default=0, description="プルーニング後推定トークン数")
    tokens_saved: int = Field(default=0, description="削減トークン数")
    token_reduction_rate: float = Field(default=0.0, description="削減率 (0.0〜1.0)")
    stats: Dict[str, Any] = Field(default_factory=dict, description="詳細統計情報")
