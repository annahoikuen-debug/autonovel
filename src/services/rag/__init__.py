"""後方互換 shim: 実体は src/integrations/rag/ に移設済み。"""
from __future__ import annotations

import importlib
import sys

from src.integrations.rag import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]


def __getattr__(name: str):
    """サブモジュールを src.integrations.rag にリダイレクト (PEP 562)。"""
    target = f"src.integrations.rag.{name}"
    try:
        module = importlib.import_module(target)
    except ModuleNotFoundError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    sys.modules[f"{__name__}.{name}"] = module
    return module
