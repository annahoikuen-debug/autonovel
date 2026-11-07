"""src/schemas パッケージ（後方互換 shim）。

実体は src/domain/schemas/easy_mode.py に移設済み。
"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.schemas.__init__ is deprecated; use src.domain.schemas.easy_mode.py instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.domain.schemas.easy_mode import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
