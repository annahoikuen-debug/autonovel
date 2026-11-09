"""モデル単価登録テスト (M0: 計測基盤)。

MODEL_PRICING に未登録のモデルがルーティング対象になっていると、
コスト計上が $0 として無言化される。_DEFAULTS の全モデルが
MODEL_PRICING に正の単価で登録されていることを保証する。
"""

from __future__ import annotations

from src.config.cost_optimization import MODEL_PRICING
from src.llm.model_router import _DEFAULTS


def test_all_default_models_have_positive_pricing():
    """_DEFAULTS の全モデルが MODEL_PRICING に正の単価で存在する。"""
    for purpose, model_name in _DEFAULTS.items():
        assert model_name in MODEL_PRICING, (
            f"purpose={purpose!r} のモデル {model_name!r} が MODEL_PRICING に未登録"
        )
        pricing = MODEL_PRICING[model_name]
        assert pricing["input"] > 0, f"{model_name}: input 単価が正でない"
        assert pricing["output"] > 0, f"{model_name}: output 単価が正でない"


def test_no_zero_cost_model_in_defaults():
    """未登録モデルを $0 で無言化する回帰防止。"""
    for purpose, model_name in _DEFAULTS.items():
        assert model_name in MODEL_PRICING, (
            f"purpose={purpose!r}: {model_name!r} 未登録 (コスト無言化のリスク)"
        )
