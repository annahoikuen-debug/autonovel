"""PLAN_S1 P3: 伏線 LLM 第 4 投票の SSOT 設定アクセス。

``config/audit_calibration.yaml`` の ``foreshadowing:`` セクション (P3 で追加) を
``calibration_store.get_calibration()`` 経由で読み、投票モードの正規化を行う。

優先順位: 環境変数 ``ENABLE_FORESHADOW_LLM_VOTE`` > yaml > コード内デフォルト
(改善 #9 M4-B パターン踏襲)。

mode:
- ``off``      : LLM を呼ばない (既定。現行配点 35/40/25 で完全後方互換 / P1)
- ``shadow``   : LLM 票を記録のみに使い、判定は現行配点のまま (P4)
- ``mainline`` : LLM 票を SSOT 配点 (35/30/20/15) で加算する
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional

from src.audit.calibration_store import get_calibration

logger = logging.getLogger(__name__)

VoteMode = Literal["off", "shadow", "mainline"]

# 影モード中に判定へ使う legacy 配点 (現行 EnsembleJudge の値と同一 / P4 契約)
LEGACY_WEIGHTS: Dict[str, int] = {"contract": 35, "metadata": 40, "syntax": 25, "llm_vote": 0}
LEGACY_THRESHOLDS: Dict[str, int] = {"resolved": 75, "progressed": 35}
LEGACY_NO_METADATA_THRESHOLDS: Dict[str, int] = {"resolved": 55, "progressed": 15}


def normalize_vote_mode(raw: Any) -> VoteMode:
    """``ENABLE_FORESHADOW_LLM_VOTE`` の生値を mode へ正規化する。

    ``_env_to_value`` が 1/0 をブール化するため、ブールも受け入れる。
    未知値は off に倒す (get_spine_quality パターン踏襲)。
    """
    if raw is True:
        return "mainline"
    if raw is False:
        return "off"
    value = str(raw).strip().lower()
    if value in ("shadow",):
        return "shadow"
    if value in ("mainline", "on", "1", "true", "yes", "enable", "enabled"):
        return "mainline"
    return "off"


def get_foreshadowing_vote_config() -> Dict[str, Any]:
    """SSOT から投票設定を取得する (必ず dict を返す = fail-open)。"""
    try:
        calibration = get_calibration()
        section = calibration.get("foreshadowing")
        if not isinstance(section, dict):
            return _default_config()
        config = dict(_default_config())
        config.update({k: v for k, v in section.items() if v is not None})
        config["mode"] = normalize_vote_mode(config.get("mode", "off"))
        return config
    except Exception as exc:  # noqa: BLE001 - SSOT 読み込み失敗でも off で継続
        logger.debug("foreshadowing vote config load skipped: %s", exc)
        return _default_config()


def _default_config() -> Dict[str, Any]:
    return {
        "mode": "off",
        "weights": dict(LEGACY_WEIGHTS),
        "thresholds": dict(LEGACY_THRESHOLDS),
        "no_metadata_thresholds": dict(LEGACY_NO_METADATA_THRESHOLDS),
        "temperature": 0.2,
    }


def get_vote_mode() -> VoteMode:
    """現在の投票モードを返す (off / shadow / mainline)。"""
    return get_foreshadowing_vote_config()["mode"]


def is_vote_enabled() -> bool:
    """LLM 投票を呼ぶべきか (shadow / mainline)。off では False (LLM 0 回 / P1)。"""
    return get_vote_mode() != "off"


def build_judge_params(mode: VoteMode) -> tuple[Optional[Dict[str, int]], Optional[Dict[str, int]]]:
    """EnsembleJudge へ渡す (weights, thresholds) を mode に応じて返す。

    - off / shadow: (None, None) = EnsembleJudge 内蔵の legacy 値 (第 4 票 weight 0 →
      判定に影響しない / P4 契約)
    - mainline: SSOT 配点 (35/30/20/15) と閾値 (no_metadata_* を含むフラット dict)
    """
    if mode == "mainline":
        config = get_foreshadowing_vote_config()
        weights = dict(config.get("weights") or LEGACY_WEIGHTS)
        thresholds_src = dict(config.get("thresholds") or LEGACY_THRESHOLDS)
        no_metadata_src = dict(config.get("no_metadata_thresholds") or LEGACY_NO_METADATA_THRESHOLDS)
        thresholds = {
            "resolved": int(thresholds_src.get("resolved", 75)),
            "progressed": int(thresholds_src.get("progressed", 35)),
            "no_metadata_resolved": int(no_metadata_src.get("resolved", 55)),
            "no_metadata_progressed": int(no_metadata_src.get("progressed", 15)),
        }
        return weights, thresholds
    return None, None  # legacy (現行) 動作


__all__ = [
    "LEGACY_THRESHOLDS",
    "LEGACY_WEIGHTS",
    "VoteMode",
    "build_judge_params",
    "get_foreshadowing_vote_config",
    "get_vote_mode",
    "is_vote_enabled",
    "normalize_vote_mode",
]
