import io, json
from src.services.cadence.compound_merger import CompoundSentenceMerger as M
m = M()
cases = ['彼は行った。','彼は書いた。','彼は怒った。','彼は勝った。','彼は跳んだ。','彼は読んだ。','彼はAppendえた。','Outside。','走った。','跳んだ。','見た。','笑った。','静かであった。','それは夢だった。','彼は走っていた。','彼は話していた。','彼は逃げた。','彼は伝えた。','彼は抜けた。','彼は止めた。','彼は溺れた。','Earlier。']
out = {s: m.convert_to_conjunctive(s) for s in cases}
out['red1'] = m.reduce_consecutive_endings(['走った。','跳んだ。','見た。','笑った。'], max_consecutive=2)
out['red2'] = m.reduce_consecutive_endings(['走った。','  ','跳んだ。','見た。'], max_consecutive=2)
out['red3'] = m.reduce_consecutive_endings(['走った。','跳んだ。','見た。'], max_consecutive=2)
out['red4'] = m.reduce_consecutive_endings(['走った。','跳んだ。','見た。','笑った。'], max_consecutive=2)
out['m1'] = m.merge_sentences('彼は走った。','早かった。')
with io.open('tmp/probe_cadence.json','w',encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print('ok')
