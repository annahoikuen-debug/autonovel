"""DSP Tension Balancer package."""

# `Beat` / `BeatType` / `CorrectionAction` は DSP 固有の型ではなく
# 上位パッケージの共通モデルに定義されている
# （src/narrative_balancer/models.py）。従来ここは
# `dsp.models` から import しており、DSPConfig 等と同じモジュールに
# 存在しないため ImportError が発生していた。
# その結果 `src.narrative_balancer.dsp` を import する 54 個のテストファイルが
# collection ERROR になり、**そのテストは一度も実行されていなかった**。
from src.narrative_balancer.models import (
    Beat,
    BeatType,
    CorrectionAction,
)
from src.narrative_balancer.dsp.models import (
    DSPConfig,
    ImpulseConfig,
    SagDetection,
    TensionSignal,
)
from src.narrative_balancer.dsp.ports import Corrector, TensionAnalyzer
from src.narrative_balancer.dsp.balancer import DSPTensionBalancer
from src.narrative_balancer.dsp.factory import create_dsp_balancer

__all__ = [
    "Beat",
    "BeatType",
    "CorrectionAction",
    "DSPConfig",
    "ImpulseConfig",
    "SagDetection",
    "TensionSignal",
    "Corrector",
    "TensionAnalyzer",
    "DSPTensionBalancer",
    "create_dsp_balancer",
]
