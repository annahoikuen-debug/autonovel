from __future__ import annotations

"""AI 判定器キャリブレーション設定ストア (M4-B: SSOT 読み込み)。

config/audit_calibration.yaml を一元管理し、環境変数で上書き可能にする。

優先順位:
  環境変数 > config/audit_calibration.yaml > コード内デフォルト

lru_cache でキャッシュし、繰り返しのファイル読み込みを避ける。
プロンプト/モデル変更時は evaluator_version を変更してキャッシュを無効化すること。
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CALIBRATION: dict[str, Any] = {
    "version": 1,
    "gate": {
        "mode": "absolute",
        "absolute_threshold": 70.0,
        "advisory_threshold": 80.0,
        "percentile": {
            "window": 200,
            "lower_pct": 30,
            "fallback_to_absolute": True,
        },
        "cliche_max": 3,
        "weights": {"quantitative": 0.4, "qualitative": 0.6},
    },
    "pairwise": {
        "enabled": False,
        "shadow_enabled": False,
        "anchor_count": 3,
    },
    "panel": {
        "enabled": False,
        "judges": [],
    },
    "score_calibration": {
        "priors_source": "builtin",
    },
    "bias_correction": {
        "enabled": False,
        "config_path": "config/llm_bias_correction.yaml",
    },
    "evaluator_version": "1.0",
}

# 環境変数名と設定パスのマッピング
ENV_TO_PATH: dict[str, tuple[str, ...]] = {
    "AUDIT_GATE_THRESHOLD": ("gate", "absolute_threshold"),
    "AUDIT_GATE_ADVISORY_THRESHOLD": ("gate", "advisory_threshold"),
    "AUDIT_CLIE_MAX": ("gate", "cliche_max"),
    "AUDIT_QUANTITATIVE_WEIGHT": ("gate", "weights", "quantitative"),
    "AUDIT_QUALITATIVE_WEIGHT": ("gate", "weights", "qualitative"),
    "ENABLE_PAIRWISE": ("pairwise", "enabled"),
    "ENABLE_PAIRWISE_SHADOW": ("pairwise", "shadow_enabled"),
    "ENABLE_PANEL": ("panel", "enabled"),
    "EVALUATOR_VERSION": ("evaluator_version",),
}


def _env_to_value(raw: str) -> Any:
    """環境変数の文字列を適切な型に変換する。"""
    low = raw.strip().lower()
    if low in ("true", "1", "yes", "on"):
        return True
    if low in ("false", "0", "no", "off"):
        return False
    # 数値変換を試みる
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """2 つの辞書を深くマージする (override が優先)。"""
    result = dict(base)
    for key, val in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(val, dict)
        ):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """環境変数で設定を上書きする。"""
    result = dict(config)
    for env_name, path in ENV_TO_PATH.items():
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        value = _env_to_value(raw)
        # パスを辿って設定を更新
        cursor = result
        for key in path[:-1]:
            if key not in cursor or not isinstance(cursor[key], dict):
                cursor[key] = {}
            cursor = cursor[key]
        cursor[path[-1]] = value
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    """YAML ファイルを読み込む。存在しない場合は空辞書。"""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return {}
    return data


@lru_cache(maxsize=1)
def get_calibration(
    config_path: str | Path = "config/audit_calibration.yaml",
) -> dict[str, Any]:
    """キャリブレーション設定を取得する (キャッシュ付き)。

    Args:
        config_path: 設定ファイルのパス。相対パスはカレントディレクトリ基準。

    Returns:
        マージ済みの設定辞書 (deep copy されて呼び出し元に返される)。
    """
    import copy

    yaml_data = _load_yaml(Path(config_path))
    config = _deep_merge(DEFAULT_CALIBRATION, yaml_data)
    config = _apply_env_overrides(config)
    return copy.deepcopy(config)


def get_gate_threshold() -> float:
    """ゲート閾値を取得する (後方互換のためのヘルパー)。"""
    return float(get_calibration()["gate"]["absolute_threshold"])


def get_effective_gate_threshold() -> float:
    """実効ゲート閾値を取得する。

    gate.mode が "percentile" の場合、環境変数 AUDIT_PERCENTILE_THRESHOLD
    (スクリプトで週次算出) があればそれを返し、なければ
    absolute_threshold にフォールバックする (コールドスタート対策)。
    """
    config = get_calibration()
    if config["gate"]["mode"] == "percentile":
        env_val = os.environ.get("AUDIT_PERCENTILE_THRESHOLD")
        if env_val is not None:
            try:
                return float(env_val)
            except ValueError:
                pass
    return float(config["gate"]["absolute_threshold"])


def get_advisory_threshold() -> float:
    """Advisory 閾値を取得する。"""
    return float(get_calibration()["gate"]["advisory_threshold"])


def get_cliche_max() -> int:
    """AI 定型上限を取得する。"""
    return int(get_calibration()["gate"]["cliche_max"])


def get_weights() -> tuple[float, float]:
    """定量・定性重みを (quantitative, qualitative) で取得する。"""
    w = get_calibration()["gate"]["weights"]
    return float(w["quantitative"]), float(w["qualitative"])


def is_pairwise_enabled() -> bool:
    """ペアワイズが有効か。"""
    return bool(get_calibration()["pairwise"]["enabled"])


def is_pairwise_shadow_enabled() -> bool:
    """ペアワイズシャドウモードが有効か。"""
    return bool(get_calibration()["pairwise"]["shadow_enabled"])


def is_panel_enabled() -> bool:
    """3 系統判定パネルが有効か。"""
    return bool(get_calibration()["panel"]["enabled"])


def get_evaluator_version() -> str:
    """評価プロトコルバージョンを取得する。"""
    return str(get_calibration()["evaluator_version"])


def clear_cache() -> None:
    """キャッシュをクリアする (主にテスト用)。"""
    get_calibration.cache_clear()


__all__ = [
    "get_calibration",
    "get_gate_threshold",
    "get_effective_gate_threshold",
    "get_advisory_threshold",
    "get_cliche_max",
    "get_weights",
    "is_pairwise_enabled",
    "is_pairwise_shadow_enabled",
    "is_panel_enabled",
    "get_evaluator_version",
    "clear_cache",
    "DEFAULT_CALIBRATION",
]
