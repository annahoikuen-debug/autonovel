"""TRACK-A read-only audit, part 2. Throwaway."""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config.story_spine.loader as loader  # noqa: E402
from config.story_spine import LENGTHS, MARKETS, PATTERNS  # noqa: E402
from config.story_spine.beat import BEAT_VOCABULARY  # noqa: E402
from src.services import spine_resolver as sr  # noqa: E402
from src.services.structure_validator import load_pattern_beats, validate  # noqa: E402
from src.services.spine_resolver import resolve_spine  # noqa: E402

print("A. merged duty text quality (truncation)")
for p in ("exile_rise", "detective_mystery", "horror_dread"):
    for eps in (1, 2, 3):
        sp = resolve_spine(p, "short", "general", eps)
        for b in sp.beats:
            flag = "  <-- TRUNCATED?" if b.duty.count("。") == 0 and not b.duty.endswith("、") else ""
            print(f"  {p[:12]:12s}@{eps} {b.key:20s} len={len(b.duty):2d} {b.duty}{flag}")
        print()

print("B. spine.at() hides compressed beats (1..eps shared)")
sp = resolve_spine("exile_rise", "short", "general", 2)
print("  beats:", [(b.key, b.ep_start, b.ep_end, b.tension) for b in sp.beats])
print("  at(1) ->", sp.at(1).key, "tension", sp.at(1).tension)
print("  at(2) ->", sp.at(2).key, "tension", sp.at(2).tension)

print()
print("C. validate() false-healthy when required_beats resolves empty")
loader.PATTERNS["__broken__"] = {
    "name": "壊れたパターン",
    "beats": [{"key": "no_such_beat", "span": [0.0, 1.0]}],
}
r = validate([{"chapter_number": i, "tension": 5} for i in range(1, 11)], pattern_key="__broken__")
print("  result:", {k: r[k] for k in ("pattern_key", "required_beat_count", "missing_beats", "is_healthy", "alignment")})
print("  load_pattern_beats:", load_pattern_beats("__broken__"))
del loader.PATTERNS["__broken__"]

print()
print("D. malformed YAML entry -> hard exception in resolve_spine")
loader.PATTERNS["__no_span__"] = {"name": "x", "beats": [{"key": "inciting"}]}
try:
    resolve_spine("__no_span__", "short", "general", 5)
    print("  no exception (unexpected)")
except Exception as exc:  # noqa: BLE001
    print(f"  raised {type(exc).__name__}: {exc}")
loader.PATTERNS["__no_span__"] = {"name": "x", "beats": [{"span": [0.0, 1.0]}]}
try:
    resolve_spine("__no_span__", "short", "general", 5)
except Exception as exc:  # noqa: BLE001
    print(f"  raised {type(exc).__name__}: {exc}")
loader.PATTERNS["__no_span__"] = {"name": "x", "beats": "notalist"}
try:
    resolve_spine("__no_span__", "short", "general", 5)
except Exception as exc:  # noqa: BLE001
    print(f"  raised {type(exc).__name__}: {exc}")
loader.PATTERNS["__no_span__"] = {"name": "x", "beats": [{"key": "inciting", "span": [0.0, 5.0]}]}
try:
    sp2 = resolve_spine("__no_span__", "short", "general", 5)
    print("  absolute span 5.0 accepted silently ->", [(b.key, b.ep_start, b.ep_end) for b in sp2.beats])
except Exception as exc:  # noqa: BLE001
    print(f"  raised {type(exc).__name__}: {exc}")
loader.PATTERNS["__no_span__"] = {"name": "x", "beats": [{"key": "inciting", "span": [0.9, 1.0]}]}
try:
    sp2 = resolve_spine("__no_span__", "short", "general", 5)
    print("  span starting at 0.9 accepted ->", [(b.key, b.ep_start, b.ep_end) for b in sp2.beats])
except Exception as exc:  # noqa: BLE001
    print(f"  raised {type(exc).__name__}: {exc}")
del loader.PATTERNS["__no_span__"]

print()
print("E. validator 'expected phase' comes from BEAT_VOCABULARY, spine from yaml span")
worst = []
for p in PATTERNS:
    req = {b["key"]: b["phase"] for b in load_pattern_beats(p)["required_beats"]}
    for b in PATTERNS[p]["beats"]:
        yaml_mid = sum(b["span"]) / 2
        worst.append((abs(yaml_mid - req.get(b["key"], yaml_mid)), p, b["key"], yaml_mid, req.get(b["key"])))
worst.sort(reverse=True)
for w in worst[:6]:
    print(f"  |diff|={w[0]:.3f} {w[1]}.{w[2]} yaml_mid={w[3]:.3f} validator_phase={w[4]}")
print(f"  mean |diff| = {sum(w[0] for w in worst)/len(worst):.3f} over {len(worst)} beats")

print()
print("F. alignment of a FAITHFUL spine (self-consistency of validate)")
bad = []
for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
    lo, hi = LENGTHS[l]["eps_range"]
    for eps in (lo, (lo + hi) // 2, hi):
        sp = resolve_spine(p, l, m, eps)
        chapters = [{"chapter_number": ep, "tension": sp.at(ep).tension} for ep in range(1, eps + 1)]
        r = validate(chapters, pattern_key=p)
        if r["alignment"] < 1.0 or not r["is_healthy"]:
            bad.append((r["alignment"], r["is_healthy"], p, l, m, eps,
                        [x["key"] for x in r["missing_beats"]]))
print("  faithful spines NOT scoring 1.0:", len(bad), "of", len(PATTERNS)*len(LENGTHS)*len(MARKETS)*3)
for b in bad[:12]:
    print("   ", b)

print()
print("G. climax position relative range across whole matrix (non-web)")
out = []
for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
    lo, hi = LENGTHS[l]["eps_range"]
    for eps in (lo, (lo + hi) // 2, hi):
        sp = resolve_spine(p, l, m, eps)
        c = [b for b in sp.beats if b.key == "climax"]
        if not c:
            out.append((None, p, l, m, eps))
            continue
        c = c[0]
        rel = ((c.ep_start + c.ep_end) / 2) / eps
        out.append((rel, p, l, m, eps))
rels = [o[0] for o in out if o[0] is not None]
print(f"  cases={len(out)} min={min(rels):.3f} max={max(rels):.3f} mean={sum(rels)/len(rels):.3f}")
low = sorted(o for o in out if o[0] is not None)[:5]
high = sorted(o for o in out if o[0] is not None)[-5:]
print("  lowest:", [(round(a, 3), b, c, d, e) for a, b, c, d, e in low])
print("  highest:", [(round(a, 3), b, c, d, e) for a, b, c, d, e in high])
print("  missing climax:", [o for o in out if o[0] is None])

print()
print("H. midpoint position range")
out = []
for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
    lo, hi = LENGTHS[l]["eps_range"]
    for eps in (lo, (lo + hi) // 2, hi):
        sp = resolve_spine(p, l, m, eps)
        c = [b for b in sp.beats if b.key == "midpoint_reversal"]
        if c:
            out.append((((c[0].ep_start + c[0].ep_end) / 2) / eps, p, l, m, eps))
rels = [o[0] for o in out]
print(f"  cases={len(out)} min={min(rels):.3f} max={max(rels):.3f}")
print("  lowest:", [(round(a, 3), b, c, d, e) for a, b, c, d, e in sorted(out)[:5]])
print("  highest:", [(round(a, 3), b, c, d, e) for a, b, c, d, e in sorted(out)[-5:]])

print()
print("I. first-beat is a hook? across matrix")
HOOK = ("inciting", "humiliation", "cold_open", "revelation")
bad = []
for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
    lo, hi = LENGTHS[l]["eps_range"]
    for eps in (lo, (lo + hi) // 2, hi, 1, 2, 3, 4, 5):
        k = resolve_spine(p, l, m, eps).keys
        if k[0] not in HOOK:
            bad.append((p, l, m, eps, k[0], k[:3]))
print("  first-not-hook cases:", len(bad))
for b in bad[:10]:
    print("   ", b)

print()
print("J. min_beats from lengths.yaml honoured?")
for lk, lv in LENGTHS.items():
    lo, hi = lv["eps_range"]
    for eps in (lo, hi):
        n = len(resolve_spine("exile_rise", lk, "web", eps).beats)
        if n < lv["min_beats"]:
            print(f"  {lk}@{eps}: beats={n} < min_beats={lv['min_beats']}")
print("  (blank = honoured for exile_rise)")

print()
print("K. hook_window_eps honoured? (first hook beat must land within N eps)")
for lk, lv in LENGTHS.items():
    lo, hi = lv["eps_range"]
    for p in PATTERNS:
        for eps in (lo, hi):
            sp = resolve_spine(p, lk, "web", eps)
            first_hook = next((b for b in sp.beats if b.key in HOOK), None)
            if first_hook and first_hook.ep_start > lv["hook_window_eps"]:
                print(f"  {p} {lk}@{eps}: first hook {first_hook.key} starts at ep{first_hook.ep_start} > {lv['hook_window_eps']}")
                break
print("  (blank = honoured)")

print()
print("L. duplicated keys inside one resolved spine")
dup = []
for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
    lo, hi = LENGTHS[l]["eps_range"]
    for eps in (lo, (lo + hi) // 2, hi, 1, 2, 3):
        k = resolve_spine(p, l, m, eps).keys
        if len(k) != len(set(k)):
            dup.append((p, l, m, eps, [x for x in set(k) if k.count(x) > 1]))
print("  spines with duplicate beat keys:", len(dup))
for d in dup[:10]:
    print("   ", d)
