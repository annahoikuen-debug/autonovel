"""STORY_SPINE: YAML データの読み込み（契約凍結 2026-09-29）。

方針:
- ファイルが存在しなくても例外を投げない（A1 時点では中身が空でよい）。
- 未知キーは例外を投げず、既定値へフォールバックする。
  B トラックの 12 ステップを壊さないため。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent

_DATA_FILES = {
    "PATTERNS": "patterns.yaml",
    "LENGTHS": "lengths.yaml",
    "MARKETS": "markets.yaml",
    "CARDS": "cards.yaml",
}

_FALLBACKS = {
    "pattern": "exile_rise",
    "length": "novella",
    "market": "general",
}


def _load(filename: str) -> dict[str, Any]:
    path = BASE_DIR / filename
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.error("YAML の解析に失敗: %s (%s)", filename, exc)
        return {}
    return data if isinstance(data, dict) else {}


PATTERNS: dict[str, Any] = _load(_DATA_FILES["PATTERNS"])
LENGTHS: dict[str, Any] = _load(_DATA_FILES["LENGTHS"])
MARKETS: dict[str, Any] = _load(_DATA_FILES["MARKETS"])
CARDS: dict[str, Any] = _load(_DATA_FILES["CARDS"])


def _resolve(table: dict[str, Any], key: str, kind: str) -> Any:
    """未知キーは既定値へフォールバックする。None は決して返さない。"""
    hit = table.get(key)
    if hit is not None:
        return hit
    fallback = _FALLBACKS[kind]
    logger.debug("未知の %s '%s' を既定 '%s' にフォールバック", kind, key, fallback)
    return table.get(fallback)


def get_pattern(key: str) -> Any:
    return _resolve(PATTERNS, key, "pattern")


def get_length(key: str) -> Any:
    return _resolve(LENGTHS, key, "length")


def get_market(key: str) -> Any:
    return _resolve(MARKETS, key, "market")


def get_card(key: str) -> Any | None:
    """カードは未知キーで None を返す（呼び出し側：B トラックのカード選択 UI）。"""
    return CARDS.get(key)


__all__ = [
    "BASE_DIR",
    "CARDS",
    "LENGTHS",
    "MARKETS",
    "PATTERNS",
    "get_card",
    "get_length",
    "get_market",
    "get_pattern",
]
