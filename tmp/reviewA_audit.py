"""TRACK-A read-only audit. Throwaway. Prints findings only."""
from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.story_spine import CARDS, LENGTHS, MARKETS, PATTERNS, get_card, get_length, get_market, get_pattern  # noqa: E402
from config.story_spine.beat import ARTIFACTS, BEAT_VOCABULARY, ROLES  # noqa: E402
from src.services.spine_resolver import resolve_spine  # noqa: E402
from src.services.structure_validator import validate, validate_spine  # noqa: E402

print("=" * 78)
print("0. counts")
print("=" * 78)
print("vocab:", len(BEAT_VOCABULARY), "patterns:", len(PATTERNS), "lengths:", len(LENGTHS),
      "markets:", len(MARKETS), "cards:", len(CARDS))

print()
print("=" * 78)
print("1. vocabulary order vs role (role blocks should be contiguous?)")
print("=" * 78)
prev_role = None
for k, b in BEAT_VOCABULARY.items():
    if b.role != prev_role:
        print(f"  {prev_role} -> {b.role} at {k} span={b.span}")
        prev_role = b.role
print("  roles used:", sorted({b.role for b in BEAT_VOCABULARY.values()}), "ROLES:", ROLES)
print("  interlude role:", BEAT_VOCABULARY["interlude"].role, BEAT_VOCABULARY["interlude"].span)

print()
print("=" * 78)
print("2. patterns.yaml strict span checks (overlap / ordering / end coverage)")
print("=" * 78)
overlaps = []
end_mismatch = []
start_mismatch = []
for pk, pat in PATTERNS.items():
    beats = pat["beats"]
    for i in range(1, len(beats)):
        prev_e = beats[i - 1]["span"][1]
        cur_s = beats[i]["span"][0]
        if cur_s < prev_e:
            overlaps.append(f"{pk}: {beats[i-1]['key']}[..{prev_e}] overlaps {beats[i]['key']}[{cur_s}..]")
    if beats[0]["span"][0] != 0.0:
        start_mismatch.append(f"{pk}: first starts at {beats[0]['span'][0]}")
    if beats[-1]["span"][1] != 1.0:
        end_mismatch.append(f"{pk}: last ends at {beats[-1]['span'][1]}")
print("  overlaps:", overlaps or "none")
print("  first-span!=0:", start_mismatch or "none")
print("  last-span!=1.0:", end_mismatch or "none")
tension_span = []
for pk, pat in PATTERNS.items():
    for b in pat["beats"]:
        v = BEAT_VOCABULARY[b["key"]]
        if abs(sum(b["span"]) / 2 - sum(v.span) / 2) > 0.001:
            tension_span.append(f"{pk}.{b['key']}: yaml_span={b['span']} vocab_span={v.span}")
print(f"  pattern span != vocabulary span: {len(tension_span)} of "
      f"{sum(len(p['beats']) for p in PATTERNS.values())}")
for t in tension_span[:8]:
    print("   ", t)

print()
print("=" * 78)
print("3. cards cross references")
print("=" * 78)
try:
    from config import STYLE_DEFINITIONS
    styles = set(STYLE_DEFINITIONS)
except Exception as exc:  # noqa: BLE001
    styles = set()
    print("  STYLE_DEFINITIONS unavailable:", exc)
bad_style = {c["style_key"] for c in CARDS.values()} - styles
print("  card style_keys not in STYLE_DEFINITIONS:", sorted(bad_style) or "none")
print("  STYLE_DEFINITIONS keys sample:", sorted(styles)[:12])
print("  cards per length:", {k: sum(1 for c in CARDS.values() if c["length"] == k) for k in LENGTHS})
print("  cards per market:", {k: sum(1 for c in CARDS.values() if c["market"] == k) for k in MARKETS})
print("  cards whose market_hint excludes card market:")
for ck, c in CARDS.items():
    hint = PATTERNS[c["pattern"]].get("market_hint", [])
    if c["market"] not in hint:
        print(f"    {ck}: pattern={c['pattern']} market={c['market']} hint={hint}")

print()
print("=" * 78)
print("4. strict coverage: covered list must equal 1..eps (no dup / no gap)")
print("=" * 78)
bad = []
overlap_cases = []
for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
    lo, hi = LENGTHS[l]["eps_range"]
    for eps in (lo, (lo + hi) // 2, hi, 1, 2, 3, eps_extra := 7):
        sp = resolve_spine(p, l, m, eps)
        cov = [n for b in sp.beats for n in range(b.ep_start, b.ep_end + 1)]
        if sorted(set(cov)) != list(range(1, eps + 1)):
            bad.append(f"{p} x {l} x {m} @{eps}: missing={sorted(set(range(1,eps+1))-set(cov))[:6]}")
        if len(cov) != len(set(cov)):
            overlap_cases.append(f"{p} x {l} x {m} @{eps}: {len(cov)-len(set(cov))} duplicated eps")
print("  coverage failures:", len(bad))
for b in bad[:10]:
    print("   ", b)
print("  overlap cases (intentional only when len(beats)>eps):", len(overlap_cases))
for b in overlap_cases[:10]:
    print("   ", b)

print()
print("=" * 78)
print("5. 3 invariants over the whole matrix (hook first / mid / climax last)")
print("=" * 78)
HOOK = ("inciting", "humiliation", "cold_open", "revelation")
viol = []
for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
    lo, hi = LENGTHS[l]["eps_range"]
    for eps in (1, 2, 3, 4, lo, (lo + hi) // 2, hi):
        sp = resolve_spine(p, l, m, eps)
        k = sp.keys
        if k[0] not in HOOK:
            viol.append(f"{p} x {l} x {m} @{eps}: first={k[0]}")
        if "midpoint_reversal" not in k:
            viol.append(f"{p} x {l} x {m} @{eps}: no midpoint")
        if "climax" not in k:
            viol.append(f"{p} x {l} x {m} @{eps}: no climax")
        if k[-1] != "climax" and m != "web":
            viol.append(f"{p} x {l} x {m} @{eps}: last={k[-1]}")
print("  violations:", len(viol))
for v in viol[:25]:
    print("   ", v)

print()
print("=" * 78)
print("6. climax relative position: resolver output vs declared yaml span")
print("=" * 78)
rows = []
for p in ("exile_rise", "detective_mystery", "slow_life", "healing_care", "dungeon_conqueror", "space_odyssey"):
    declared = [b["span"] for b in PATTERNS[p]["beats"] if b["key"] == "climax"][0]
    for eps in (10, 40, 100, 300):
        sp = resolve_spine(p, "long_serial", "web", eps)
        c = [b for b in sp.beats if b.key == "climax"][0]
        rel = ((c.ep_start + c.ep_end) / 2) / eps
        rows.append(f"  {p:20s} eps={eps:4d} declared_mid={(declared[0]+declared[1])/2:.3f} actual_rel={rel:.3f} eps_range={c.ep_start}-{c.ep_end}")
print("\n".join(rows))

print()
print("=" * 78)
print("7. does resolver honour spans at all? compare first beat start vs declared")
print("=" * 78)
for p in ("exile_rise", "horror_dread"):
    decl = PATTERNS[p]["beats"][0]
    for eps in (4, 10, 40):
        sp = resolve_spine(p, "long_serial", "general", eps)
        b0 = sp.beats[0]
        print(f"  {p}: declared first={decl['key']}@{decl['span']} actual={b0.key}@{b0.ep_start}-{b0.ep_end} @{eps}eps")

print()
print("=" * 78)
print("8. unknown-key fallback: returned metadata vs actually used data")
print("=" * 78)
sp = resolve_spine("nope", "nope", "nope", 3)
real = resolve_spine("exile_rise", "novella", "general", 3)
print("  unknown ->", sp.pattern, sp.length, sp.market, sp.total_eps, sp.keys)
print("  exile_rise/novella/general ->", real.pattern, real.length, real.market, real.total_eps, real.keys)
print("  identical beats:", [ (b.ep_start,b.ep_end,b.key) for b in sp.beats] == [(b.ep_start,b.ep_end,b.key) for b in real.beats])
print("  get_pattern('nope') is get_pattern('exile_rise'):", get_pattern("nope") is get_pattern("exile_rise"))
print("  get_card('nope'):", get_card("nope"))
print("  get_market('nope') label:", get_market("nope").get("label"))
print("  get_length('nope') label:", get_length("nope").get("label"))

print()
print("=" * 78)
print("9. market contract: light_novel declares next_volume_hook")
print("=" * 78)
for m in MARKETS:
    sp = resolve_spine("exile_rise", "long_serial", m, 100)
    print(f"  market={m:12s} ending_contract={MARKETS[m]['ending_contract']:18s} last={sp.keys[-1]:12s} volume_hook={'volume_hook' in sp.keys}")

print()
print("=" * 78)
print("10. validate() return keys (plan A4 requires 'spine' key)")
print("=" * 78)
r = validate([{"chapter_number": i, "tension": i} for i in range(1, 21)], pattern_key="exile_rise")
print("  keys:", sorted(r))
print("  has 'spine':", "spine" in r)
print("  alignment:", r["alignment"], "required:", r["required_beat_count"], "missing:", len(r["missing_beats"]))
r2 = validate([{"chapter_number": i, "tension": i} for i in range(1, 21)], pattern_key="nope")
print("  unknown pattern -> structure:", r2["structure"], "pattern_key:", r2["pattern_key"], "required:", r2["required_beat_count"])
print("  unknown pattern still reports missing exile_rise beats:",
      [b["key"] for b in r2["missing_beats"]][:5])

print()
print("=" * 78)
print("11. validate_spine over matrix: unhealthy spines")
print("=" * 78)
bad = []
for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
    lo, hi = LENGTHS[l]["eps_range"]
    for eps in (lo, hi, 1, 2, 3):
        res = validate_spine(resolve_spine(p, l, m, eps))
        if not res["is_healthy"]:
            bad.append(f"{p} x {l} x {m} @{eps}: {res['problems']}")
print("  unhealthy:", len(bad))
for b in bad[:10]:
    print("   ", b)

print()
print("=" * 78)
print("12. Spine.at() boundary behaviour + determinism of duty merge")
print("=" * 78)
sp = resolve_spine("exile_rise", "web_volume", "web", 40)
print("  beats:", [(b.key, b.ep_start, b.ep_end) for b in sp.beats])
print("  at(0):", sp.at(0), " at(41):", sp.at(41))
print("  duties >60 chars:", [(b.key, len(b.duty)) for b in sp.beats if len(b.duty) > 60])
print("  duty ending with '..' or '、。':", [b.duty for b in sp.beats if b.duty.endswith("、。") or "。。" in b.duty])
short = resolve_spine("exile_rise", "short", "general", 2)
for b in short.beats:
    print(f"   2ep {b.key} {b.ep_start}-{b.ep_end} duty={b.duty!r}")

print()
print("=" * 78)
print("13. perf: worst case")
print("=" * 78)
t0 = time.perf_counter()
for p in PATTERNS:
    resolve_spine(p, "series", "web", 1000)
print(f"  38 x series@1000eps: {(time.perf_counter()-t0)*1000:.1f} ms")
t0 = time.perf_counter()
for p in PATTERNS:
    resolve_spine(p, "short", "general", 1)
print(f"  38 x short@1eps:     {(time.perf_counter()-t0)*1000:.1f} ms")
t0 = time.perf_counter()
for i in range(1, 2001):
    resolve_spine("exile_rise", "series", "web", i)
print(f"  eps sweep 1..2000:   {(time.perf_counter()-t0)*1000:.1f} ms")
