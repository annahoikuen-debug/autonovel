"""後方互換 shim: 実体は src/publishing/exporters/ に移設済み。"""
from __future__ import annotations

import importlib
import sys

from src.publishing.exporters import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]


def __getattr__(name: str):
    """サブモジュールを src.publishing.exporters にリダイレクト (PEP 562)。"""
    target = f"src.publishing.exporters.{name}"
    try:
        module = importlib.import_module(target)
    except ModuleNotFoundError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    sys.modules[f"{__name__}.{name}"] = module
    return module
