import io, json, sys
sys.path.insert(0, '.')
from src.services.cadence.compound_merger import CompoundSentenceMerger as M
m = M()
A = ['彼は走った。', '彼は跳んだ。', '彼は見た。', '彼は笑った。']
B = ['彼は走った。', '彼は跳んだ。', '彼は見た。', '彼は笑った。', '彼は泣いた。', '彼は怒った。']
out = {}
out['r1'] = m.reduce_consecutive_endings(A, max_consecutive=2)
out['r2'] = m.reduce_consecutive_endings(['  '] + A, max_consecutive=2)
out['r3'] = m.reduce_consecutive_endings(A[:3], max_consecutive=2)
out['r4'] = m.reduce_consecutive_endings(B, max_consecutive=2)
out['r5'] = m.reduce_consecutive_endences if False else m.reduce_consecutive_endings(A, max_consecutive=5)
out['r6'] = m.reduce_consecutive_endings(B, max_consecutive=2, max_chars=5)
with io.open('tmp/probe5.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print('ok')
