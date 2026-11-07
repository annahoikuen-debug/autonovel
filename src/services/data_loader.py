"""JSON 設定ローダー - 後方互換 shim。

F4 フェーズ: 実装は src/domain/services/data_loader.py に移設。
このモジュールは re-export 用 shim として残す。
"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.data_loader is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.domain.services.data_loader import (  # noqa: F401
    DataLoader,
)
