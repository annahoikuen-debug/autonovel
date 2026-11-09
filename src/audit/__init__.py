from __future__ import annotations

"""audit パッケージ。

監査・品質ゲート関連モジュールを提供する。

- pipeline: 監査パイプライン
- repair_planner: 修復計画
- static_rules: 静的ルール監査
- triage: トリアージ
- unified_llm_auditor: 統合LLM監査（レガシー）
- perturbation: 擾乱スイート（M1）
- judge_panel: 3系統判定パネル（M3）
"""

from src.audit.perturbation import (
    PerturbationTransform,
    PerturbationKind,
    TRANSFORM_REGISTRY,
    register,
)
from src.audit.judge_panel import (
    JudgePanel,
    JudgeSpec,
    JudgeScore,
    PanelScore,
    PairwiseVerdict,
    PanelUnavailable,
)

__all__ = [
    "PerturbationTransform",
    "PerturbationKind",
    "TRANSFORM_REGISTRY",
    "register",
    "JudgePanel",
    "JudgeSpec",
    "JudgeScore",
    "PanelScore",
    "PairwiseVerdict",
    "PanelUnavailable",
]
