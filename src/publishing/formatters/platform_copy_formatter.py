"""後方互換 shim: 実体は ``src/application/formatters/platform_copy_formatter.py``。"""

from __future__ import annotations

from src.application.formatters.platform_copy_formatter import (  # noqa: F401
    FormattedChapterPayload,
    PlatformCopyFormatter,
)

__all__ = ["FormattedChapterPayload", "PlatformCopyFormatter"]
