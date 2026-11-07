"""後方互換 shim: 実体は ``src/application/formatters/platform_copy_formatter.py``。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.publishing.formatters.platform_copy_formatter is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.application.formatters.platform_copy_formatter import (  # noqa: F401
    FormattedChapterPayload,
    PlatformCopyFormatter,
)

__all__ = ["FormattedChapterPayload", "PlatformCopyFormatter"]
