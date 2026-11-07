"""後方互換 shim: 実体は src/engine/narrative/ に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.narrative.__init__ is deprecated; use src.engine.narrative instead",
    DeprecationWarning,
    stacklevel=2,
)
import importlib
import sys

from src.engine.narrative import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]


def __getattr__(name: str):
    """サブモジュールを src.engine.narrative にリダイレクト (PEP 562)。"""
    target = f"src.engine.narrative.{name}"
    try:
        module = importlib.import_module(target)
    except ModuleNotFoundError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    sys.modules[f"{__name__}.{name}"] = module
    return module
