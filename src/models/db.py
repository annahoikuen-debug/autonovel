from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from src.models.base import MODEL_CONFIG_DEFAULTS


class BookDbModel(BaseModel):
    id: int
    title: str
    genre: str | None = None
    concept: str | None = None
    synopsis: str | None = None
    catchcopy: str | None = None
    target_eps: int | None = None
    style_dna: dict | str | None = None
    status: str | None = None
    created_at: datetime | None = None
    marketing_data: dict | str | None = None
    cumulative_tension: int | None = 0
    cumulative_qol: int | None = 0
    cumulative_cost: float | None = 0.0
    sanctuary_integrity: int | None = 100
    current_branch_id: int | None = None

    @property
    def style_key(self) -> str:
        """style_dna からスタイルキー（mode）を安全に取得する"""
        if isinstance(self.style_dna, dict):
            return self.style_dna.get("mode", "default")
        if isinstance(self.style_dna, str) and self.style_dna.strip():
            try:
                data = json.loads(self.style_dna)
                return data.get("mode", "default")
            except (json.JSONDecodeError, TypeError):
                return "default"
        return "default"

    model_config = MODEL_CONFIG_DEFAULTS


class BibleDbModel(BaseModel):
    id: int
    book_id: int
    settings: dict | str | None = None
    revealed: str | None = None
    version: int | None = None
    last_updated: str | None = None

    @property
    def world_settings(self) -> Any:
        """settings から WorldRules 相当のデータを取得する。"""
        if isinstance(self.settings, dict):
            return self.settings
        if isinstance(self.settings, str) and self.settings.strip():
            try:
                return json.loads(self.settings)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    model_config = MODEL_CONFIG_DEFAULTS


class BranchDbModel(BaseModel):
    """物語の分岐（Gitのブランチに相当）を管理するモデル"""

    id: int
    book_id: int
    name: str
    parent_id: int | None = None
    fork_ep_num: int | None = 0
    created_at: datetime | None = None

    model_config = MODEL_CONFIG_DEFAULTS


class CharacterDbModel(BaseModel):
    id: int
    book_id: int
    name: str | None = None
    role: str | None = None
    registry_data: dict | str | None = None

    def to_safe_dict(self) -> dict[str, Any]:
        """registry_data を辞書として安全に取得する。文字列の場合は JSON パースを行う。"""
        if isinstance(self.registry_data, dict):
            return self.registry_data
        if isinstance(self.registry_data, str) and self.registry_data.strip():
            try:
                return json.loads(self.registry_data)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    model_config = MODEL_CONFIG_DEFAULTS
