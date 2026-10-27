"""起動診断: src.backend.server の import が，消费メモリと import 時間を計測する（Windows / POSIX 両対応）。

使い方:
    python scripts/debug/import_mem_probe.py
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
import tracemalloc
from ctypes import wintypes


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _rss_mb() -> float:
    """プロセスの Resident Set Size を MB で返す。"""
    if sys.platform == "win32":

        class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        return counters.WorkingSetSize / 1024 / 1024

    import resource  # noqa: PLC0415  POSIX only

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main() -> int:
    print(f"python     = {sys.version.split()[0]}")
    print(f"executable = {sys.executable}")
    print(f"cwd        = {os.getcwd()}")
    print(f"rss(before)= {_rss_mb():.1f} MB")
    print("-" * 60)

    tracemalloc.start(1)
    t0 = time.perf_counter()
    try:
        from src.backend.server import app  # noqa: F401
    except BaseException as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - t0
        _current, peak = tracemalloc.get_traced_memory()
        print(f"IMPORT FAILED after {elapsed:.2f}s")
        print(f"  {type(exc).__name__}: {exc}")
        print(f"  rss(peak)  = {_rss_mb():.1f} MB")
        print(f"  py tracemem= {peak / 1024 / 1024:.1f} MB")
        print(f"  modules    = {len(sys.modules)}")
        return 1

    elapsed = time.perf_counter() - t0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"IMPORT OK in {elapsed:.2f}s")
    print(f"  rss(peak)  = {_rss_mb():.1f} MB")
    print(f"  py tracemem= {peak / 1024 / 1024:.1f} MB")
    print(f"  modules    = {len(sys.modules)}")
    print(f"  routes     = {len(getattr(app, 'routes', []))}")
    print("")
    print("  heavy SDKs pulled in at import time:")
    for name in ("chromadb", "openai", "google.genai", "anthropic", "sentence_transformers", "torch"):
        loaded = name in sys.modules
        print(f"    {'LOADED' if loaded else 'lazy  '}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
