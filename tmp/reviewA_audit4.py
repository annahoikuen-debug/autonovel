"""TRACK-A read-only audit, part 4. Throwaway."""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.story_spine import LENGTHS, MARKETS, PATTERNS, resolve_spine  # noqa: E402
from src.backend.engine_narrative import PacingGraph  # noqa: E402

print("W. overlap only when len(beats) > eps?")
bad = []
for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
    lo, hi = LENGTHS[l]["eps_range"]
    for eps in (lo, (lo + hi) // 2, hi, 1, 2, 3, 5, 8, 13, 21):
        sp = resolve_spine(p, l, m, eps)
        cov = [n for b in sp.beats for n in range(b.ep_start, b.ep_end + 1)]
        if len(cov) != len(set(cov)) and len(sp.beats) <= eps:
            bad.append((p, l, m, eps, len(sp.beats), len(cov)))
print("  unintended overlaps:", len(bad), bad[:5])

print()
print("X. PacingGraph length-dependence for eps >= 20")
bad = []
for eps in range(20, 401):
    for k in range(2, eps + 1, max(1, eps // 40)):
        a = PacingGraph.get_instruction(k, total_eps=eps)["instruction"]
        b = PacingGraph.get_instruction(2 * k - 1, total_eps=2 * eps - 1)["instruction"]
        if a != b:
            bad.append((eps, k, a[:10], b[:10]))
print("  mismatches (eps>=20):", len(bad), bad[:6])

print()
print("Y. G1 gate command")
import subprocess  # noqa: E402

for cmd in (
    [sys.executable, "-c",
     "from config.story_spine import BEAT_VOCABULARY, PATTERNS, LENGTHS, MARKETS, CARDS, get_pattern; print(len(BEAT_VOCABULARY))"],
    [sys.executable, "-c", "import config; print(len(config.STORY_ARCHETYPES))"],
    [sys.executable, "-c", "from config.story_spine import resolve_spine; print('lazy ok')"],
):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=Path.cwd())
    print("  ", " ".join(cmd[2:])[:70], "->", r.returncode, r.stdout.strip(), r.stderr.strip()[:80])

print()
print("Z. EASY_GENRES / PLOT_STRUCTURES leftovers in archetypes_new")
import config.archetypes_new as an  # noqa: E402

print("  has PLOT_STRUCTURES:", hasattr(an, "PLOT_STRUCTURES"))
print("  has EASY_GENRES:", hasattr(an, "EASY_GENRES"))
import json  # noqa: E402

ap = Path("config/data/archetypes.json")
if ap.exists():
    data = json.loads(ap.read_text(encoding="utf-8"))
    print("  archetypes.json top keys:", list(data)[:6])
    ps = data.get("PLOT_STRUCTURES")
    if isinstance(ps, dict):
        legacy = set(ps)
        print("  legacy json PLOT_STRUCTURES:", len(legacy))
        missing = legacy - set(PATTERNS)
        print("  legacy keys missing from patterns.yaml:", sorted(missing))
        for k in sorted(legacy)[:3]:
            e = ps[k]
            p = PATTERNS.get(k, {})
            same = (e.get("name") == p.get("name") and e.get("mid_crisis") == p.get("mid_crisis")
                    and e.get("climax_type") == p.get("climax_type"))
            print(f"   {k}: json_name={e.get('name')!r} yaml_name={p.get('name')!r} identical_fields={same}")
            print(f"      json hook={e.get('hook')!r}")
            print(f"      json endings={e.get('ending')!r} yaml endings={p.get('endings')!r}")
            print(f"      json key_tropes={e.get('key_tropes')!r} yaml tropes={p.get('tropes')!r}")

print()
print("AA. style_key consumers in src/")
import re  # noqa: E402

hits = []
for p in Path("src").rglob("*.py"):
    txt = p.read_text(encoding="utf-8", errors="ignore")
    if "style_key" in txt:
        for i, line in enumerate(txt.splitlines(), 1):
            if "style_key" in line:
                hits.append(f"{p}:{i}: {line.strip()[:110]}")
print("\n".join(hits) if hits else "  no style_key consumer in src/")

print()
print("AB. coverage of the vocabulary: which of the 34 beats are never used by any pattern?")
used = {b["key"] for p in PATTERNS.values() for b in p["beats"]}
from config.story_spine import BEAT_VOCABULARY as V  # noqa: E402

print("  unused beats:", sorted(set(V) - used))
print("  vocabulary size:", len(V), "used:", len(used & set(V)))
