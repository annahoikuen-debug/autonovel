"""後方互換 shim: 実体は src/engine/context_compression/ に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.context_compression.__init__ is deprecated; use src.engine.context_compression instead",
    DeprecationWarning,
    stacklevel=2,
)
import importlib
import sys

from src.engine.context_compression import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]


def __getattr__(name: str):
    """サブモジュールを src.engine.context_compression にリダイレクト (PEP 562)。"""
    target = f"src.engine.context_compression.{name}"
    try:
        module = importlib.import_module(target)
    except ModuleNotFoundError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    sys.modules[f"{__name__}.{name}"] = module
    return module
