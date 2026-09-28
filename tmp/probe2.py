import io, json, sys
sys.path.insert(0, '.')
from src.services.cadence.compound_merger import CompoundSentenceMerger as M
m = M()
out = {}
out['r1'] = m.reduce_consecutive_endings(['走った。', '跳んだ。', '見た。', '笑った。'], max_consecutive=2)
out['r2'] = m.reduce_consecutive_endings(['走った。', '  ', '跳んだ。', '見た。'], max_consecutive=2)
out['r3'] = m.reduce_consecutive_endings(['走った。', '跳んだ。', '見た。'], max_consecutive=2)
out['r4'] = m.reduce_consecutive_endings(['走った。', '跳んだ。', '見た。', '笑った。', '泣いた。', '怒った。'], max_consecutive=2)
out['r5'] = m.reduce_consecutive_endings(['走った。', '跳んだ。', '見た。', '笑った。'], max_consecutive=5)
out['r6'] = m.reduce_consecutive_endings(['走った。', '跳んだ。', '見た。', '笑った。', '泣いた。', '怒った。'], max_consecutive=2, max_chars=5)
with io.open('tmp/probe2.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print('ok')
