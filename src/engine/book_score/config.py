"""book_score 設定読み込み・重み取得ロジック。

src/engine/book_score/service.py から機能分割（案A+B）により新設。
旧パス ``src/engine/book_score/service.py`` は shim として残す。
"""

from __future__ import annotations

from typing import Any, Dict


def load_book_score_config(
    config_path: str = "config/book_score_weights.yaml",
) -> Dict[str, Any]:
    """YAML 設定ファイルを読み込む。

    読み込み失敗時は空 dict を返し、呼び出し側で既定値を使う。
    """
    try:
        import yaml

        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_weights_for_genre_phase(
    config: Dict[str, Any],
    genre: str = "",
    phase: str = "",
    default_weights: Dict[str, float] | None = None,
) -> Dict[str, float]:
    """ジャンルとフェーズに基づく重みを取得。

    Args:
        config: YAML 設定（``default`` / ``genre_overrides`` / ``phase_overrides`` キーを持つ）
        genre: ジャンル名（空文字なら既定のみ）
        phase: フェーズ名（空文字なら既定のみ）
        default_weights: 既定重み（未指定時は 5次元の均等配分に近い既定値）

    Returns:
        ジャンル・フェーズ適用後の重み辞書
    """
    if default_weights is None:
        default_weights = {
            "structure": 25,
            "coherency": 25,
            "factual_grounding": 20,
            "visual_textual_synergy": 15,
            "reader_experience": 15,
        }
    weights = default_weights.copy()
    if genre and genre in config.get("genre_overrides", {}):
        weights.update(config["genre_overrides"][genre])
    if phase and phase in config.get("phase_overrides", {}):
        weights.update(config["phase_overrides"][phase])
    return weights
