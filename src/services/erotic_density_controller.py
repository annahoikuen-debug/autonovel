"""
src/services/erotic_density_controller.py - 後方互換 shim。

F4 フェーズ: 実装は src/domain/services/erotic_density_controller.py に移設。
このモジュールは re-export 用 shim として残す。
"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.erotic_density_controller is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.domain.services.erotic_density_controller import (  # noqa: F401
    EroticDensityController,
)
