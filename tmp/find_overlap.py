import re
import itertools

from src.agents.enrichment.sensory import ABSTRACT_EMOTION_PATTERNS as P

items = [(e, p) for e, ps in P.items() for p in ps]

prefixes = set()
for e, p in items:
    lit = re.split(r"[\\^$.|?*+()\[\]{}]", p)[0]
    if lit:
        prefixes.add(lit)
prefixes = sorted(prefixes)


def overlapping(t):
    hits = []
    for e, ps in P.items():
        for p in ps:
            for m in re.finditer(p, t):
                hits.append((m.start(), m.end(), e, p))
    hits.sort()
    for i in range(len(hits)):
        for j in range(i + 1, len(hits)):
            if hits[i][0] < hits[j][1] and hits[j][0] < hits[i][1]:
                return hits[i], hits[j]
    return None


count = 0
for a, b in itertools.product(prefixes, repeat=2):
    t = a + b
    r = overlapping(t)
    if r:
        print(repr(t), r)
        count += 1
        if count > 10:
            break
print("total", count)
