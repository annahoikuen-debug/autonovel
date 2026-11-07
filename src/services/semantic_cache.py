"""後方互換 shim: 実体は src/integrations/semantic_cache.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.semantic_cache is deprecated; use src.integrations.semantic_cache.py instead",
    DeprecationWarning,
    stacklevel=2,
)
import importlib
import sys

from src.integrations.semantic_cache import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]


def __getattr__(name: str):
    """未公開属性を含む全属性を src.integrations.semantic_cache にリダイレクト (PEP 562)。"""
    mod = importlib.import_module("src.integrations.semantic_cache")
    if not hasattr(mod, name):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    val = getattr(mod, name)
    super_module = sys.modules[__name__]
    super_module.__dict__[name] = val
    return val
