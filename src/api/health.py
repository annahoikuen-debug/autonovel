"""
src/api/health.py - DEPRECATED: Use src.backend.routers.health instead.
Compatibility shim for legacy health router imports.
"""


import warnings

warnings.warn(
    "src.api.health is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.backend.routers.health import router

__all__ = ["router"]
