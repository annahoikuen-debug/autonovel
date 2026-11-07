"""後方互換 shim: 実体は src/publishing/illustration/image_service.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.image_service is deprecated; use src.publishing.illustration.image_service.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.publishing.illustration.image_service import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
