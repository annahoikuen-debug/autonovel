"""TRACK-A read-only audit, part 3. Throwaway."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config.story_spine.loader as loader  # noqa: E402
from config import STYLE_DEFINITIONS  # noqa: E402
from config.story_spine import CARDS, PATTERNS  # noqa: E402
from src.services import spine_resolver as sr  # noqa: E402
from src.services.structure_validator import validate  # noqa: E402
from src.services.spine_resolver import resolve_spine  # noqa: E402

print("M. duplicate-key spine, full detail")
sp = resolve_spine("guild_rebuilder", "novella", "general", 10)
for b in sp.beats:
    print(f"   {b.key:20s} {b.ep_start}-{b.ep_end}  duty={b.duty[:30]}...")

print()
print("N. why duty is duplicated: node.members after compression")
nodes = sr._nodes(PATTERNS["horror_dread"], "general", 1)
comp = sr._compress(nodes, 1)
for n in comp:
    print(f"   key={n.key:20s} members={n.members}")
nodes = sr._nodes(PATTERNS["exile_rise"], "general", 1)
for n in sr._compress(nodes, 1):
    print(f"   key={n.key:20s} members={n.members}")

print()
print("O. validate() with rising tension: is_healthy when required_beats == 0")
loader.PATTERNS["__broken__"] = {"name": "壊れ", "beats": [{"key": "nope_key", "span": [0.0, 1.0]}]}
r = validate(
    [{"chapter_number": i, "tension": i} for i in range(1, 11)],
    pattern_key="__broken__",
)
print("  ", {k: r[k] for k in ("required_beat_count", "missing_beats", "is_healthy", "climax", "alignment")})
del loader.PATTERNS["__broken__"]

print()
print("P. PacingGraph short-form coverage (eps 1..8)")
from src.backend.engine_narrative import PacingGraph  # noqa: E402

for eps in (1, 2, 3, 4, 5, 8, 20, 100):
    labels = []
    for ep in range(1, eps + 1):
        labels.append(PacingGraph.get_instruction(ep, total_eps=eps)["instruction"][:12])
    print(f"  eps={eps:4d}: {labels}")

print()
print("Q. PacingGraph: same relative position, different length, same instruction? (all k)")
bad = []
for eps in range(1, 60):
    for k in range(2, eps + 1):
        a = PacingGraph.get_instruction(k, total_eps=eps)["instruction"]
        b = PacingGraph.get_instruction(2 * k - 1, total_eps=2 * eps - 1)["instruction"]
        if a != b:
            bad.append((eps, k, a[:14], b[:14]))
print("  mismatches:", len(bad))
for x in bad[:12]:
    print("   ", x)

print()
print("R. PacingGraph constants vs BEAT_VOCABULARY spans")
from config.story_spine import BEAT_VOCABULARY as V  # noqa: E402

for const, key in (
    ("_HOOK_END", "revelation"),
    ("_FIRST_EXPLOSION_START", "first_win"),
    ("_FIRST_EXPLOSION_END", "first_win"),
    ("_CLIMAX_START", "last_stand"),
    ("_CLIMAX_END", "climax"),
):
    print(f"  PacingGraph.{const} = {getattr(PacingGraph, const)}  vs  {key}.span = {V[key].span}")
print("  is _FIRST_EXPLOSION_START reachable? pos<=_HOOK_END branch precedes it")

print()
print("S. card style_key resolution")
print("  card style_keys:", sorted({c["style_key"] for c in CARDS.values()}))
print("  STYLE_DEFINITIONS keys:", sorted(STYLE_DEFINITIONS)[:40])
print("  overlap:", sorted({c["style_key"] for c in CARDS.values()} & set(STYLE_DEFINITIONS)))
print("  preset-ish keys?", [k for k in STYLE_DEFINITIONS if "hot" in k or "cool" in k or "healing" in k or "dark" in k])

print()
print("T. Chinese comment / leftovers in TRACK-A files")
for p in (
    "src/services/spine_resolver.py",
    "src/services/structure_validator.py",
    "config/story_spine/beat.py",
    "config/story_spine/loader.py",
    "config/story_spine/__init__.py",
):
    text = Path(p).read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        if any("\u4e00" <= ch <= "\u9fff" for ch in line):
            print(f"  {p}:{i}: {line.strip()}")

print()
print("U. resolve_spine signature / contract shape")
import inspect  # noqa: E402

print("  ", inspect.signature(resolve_spine))
import config.story_spine as pkg  # noqa: E402

print("  'resolve_spine' in __all__:", "resolve_spine" in pkg.__all__)
print("  dir(pkg) has resolve_spine:", hasattr(pkg, "resolve_spine"))
ns: dict = {}
exec("from config.story_spine import *", ns)  # noqa: S102
print("  star-import exposes resolve_spine:", "resolve_spine" in ns)
print("  get_pattern returns raw dict (not dataclass):", type(pkg.get_pattern("exile_rise")).__name__)

print()
print("V. BEAT_VOCABULARY span sanity for the beats the plan calls out")
for k in ("inciting", "cold_open", "humiliation", "revelation", "first_win", "midpoint_reversal", "climax", "volume_hook", "interlude"):
    b = V[k]
    print(f"  {k:20s} role={b.role:9s} span={b.span} tension={b.tension} optional={b.optional} artifact={b.artifact}")
print("  optional=True count:", sum(1 for b in V.values() if b.optional))
