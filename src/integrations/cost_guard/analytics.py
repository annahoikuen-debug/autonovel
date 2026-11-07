"""コスト計算モジュール - 後方互換 shim。

F4 フェーズ: 実装は src/domain/services/cost_analytics.py に移設。
このモジュールは re-export 用 shim として残す。
"""

import warnings

warnings.warn(
    "src.integrations.cost_guard.analytics is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.domain.services.cost_analytics import (  # noqa: F401
    CostCalculator,
    DEFAULT_PRICING,
    _default_calculator,
    check_budget_alert,
    estimate_cost_usd,
)
