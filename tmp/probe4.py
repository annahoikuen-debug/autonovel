import sys, re
sys.path.insert(0, '.')
from src.services.cadence.compound_merger import CompoundSentenceMerger as M
m = M()
sentences = ['走った。', '跳んだ。', '見た。']
i = 0
consecutive_ta = 0
max_consecutive = 2
while i < len(sentences):
    current = sentences[i].strip()
    is_ta = bool(re.search(r"[ただ][。]$", current))
    print(i, repr(current), is_ta)
    if is_ta:
        consecutive_ta += 1
    else:
        consecutive_ta = 0
    if consecutive_ta >= max_consecutive and i + 1 < len(sentences):
        print('  try merge', repr(sentences[i+1]), m.merge_sentences(current, sentences[i+1], 60))
    i += 1
print('full', m.reduce_consecutive_endings(sentences, max_consecutive=2))
print('full no kw', m.reduce_consecutive_endings(sentences, 2))
