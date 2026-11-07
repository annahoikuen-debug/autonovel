"""src/agents/audit — 後方互換 shim。

実装は ``src/agents/audit/`` パッケージ（plot_integrity.py 等）に移設済み。
このモジュールは旧 import 経路（``from src.agents.audit import ...``）を
維持するためにパッケージから再エクスポートする。

分割は案A+B（ファイル隔離＋旧パスshim＋関連テスト全緑）に従う。
削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。
"""

from __future__ import annotations

import warnings

warnings.warn(
    "src.agents.audit is deprecated; use src.agents.audit package instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.agents.audit import (  # noqa: F401, F403
    DeAIAuditor,
    InternalLogicValidator,
    LogicalAuditor,
    PlotIntegrityMonitor,
)

# audit_screeners.py からの再エクスポート（旧 audit.py でも同等の再エクスポートを行っていた）
from src.agents.audit_screeners import (  # noqa: F401, F403
    AbilityConsistencyChecker,
    FastPlotScreener,
)

# plot_integrity.py でインポートしている extraction_service をモジュール属性として
# 再エクスポート（テストが patch("src.agents.audit.extraction_service") するため）
from src.engine.extraction_service import extraction_service  # noqa: F401

__all__ = [name for name in dir() if not name.startswith("_")]
