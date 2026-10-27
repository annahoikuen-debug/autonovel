"""実行時 import フックで「google.genai / openai / chromadb を誰_TOPレベル import したか」を特定する。

使い方:
    python scripts/debug/trace_heavy_imports.py
"""

from __future__ import annotations

import builtins
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TARGETS = ("chromadb", "openai", "google.genai", "google", "anthropic", "sentence_transformers")
HITS: dict[str, str] = {}
_real_import = builtins.__import__


def _tracing_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002, ANN001
    if name in TARGETS and name not in HITS:
        caller = "<unknown>"
        if globals:
            caller = globals.get("__name__", "<unknown>")
        HITS[name] = f"{caller} (level={level}, fromlist={fromlist})"
    return _real_import(name, globals, locals, fromlist, level)


builtins.__import__ = _tracing_import

t0 = time.perf_counter()
import src.backend.server  # noqa: F401

elapsed = time.perf_counter() - t0
builtins.__import__ = _real_import

print(f"import src.backend.server : {elapsed:.1f}s / {len(sys.modules)} modules")
print("")
for target in TARGETS:
    if target in HITS:
        print(f"  LOADED via {target:<24} <- {HITS[target]}")
    else:
        print(f"  lazy   {target}")
