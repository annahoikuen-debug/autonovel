import sys, asyncio, json, io
sys.path.insert(0, '.')
sys.path.insert(0, 'tests')
from unittest.mock import MagicMock, AsyncMock
from src.services.book_score_service import BookScoreCalculator

def make_result(value):
    res = MagicMock()
    sc = res.scalars.return_value
    if isinstance(value, list):
        sc.all.return_value = value
        sc.first.return_value = value[0] if value else None
    else:
        sc.first.return_value = value
        sc.all.return_value = [value] if value is not None else []
    return res

def make_repo(plot=None, chapter=None, illustration=None, bible=None, audit=None):
    repo = MagicMock()
    repo.save = AsyncMock(); repo.get_latest = AsyncMock()
    repo.get_all_for_book = AsyncMock(return_value=[])
    state = {"plot": plot, "chapter": chapter, "illustration": illustration, "bible": bible, "audit": audit}
    async def _execute(stmt):
        s = str(stmt)
        for t, k in [("plots","plot"),("chapters","chapter"),("illustrations","illustration"),("bibles","bible")]:
            if t in s:
                return make_result(state[k])
        return make_result(state["audit"])
    repo.session = MagicMock(); repo.session.execute = AsyncMock(side_effect=_execute)
    return repo

def chapter_obj(content=None, tension=None):
    o = MagicMock(); o.content = content; o.tension = tension; return o

out = {}
C = lambda r: BookScoreCalculator(config_path="nope.yaml", repository=r)

async def main():
    for t in ["テストテストテストテスト", "alpha beta gamma delta epsilon", "テスト テスト テスト あ い う え お", "あいうえおかきくけこさしすせそたちつてとなにぬ"]:
        out['name_'+t] = await C(make_repo(chapter=chapter_obj(content=t)))._score_coherency(1,1,None)
    text = "魔術学院の物語。" + "無関係" * 30
    bible = MagicMock(); bible.settings = json.dumps({"w":"魔術学院 皇帝 騎士団 完全別の言葉 別の語","x":5}, ensure_ascii=False)
    out['rag_med'] = await C(make_repo(chapter=chapter_obj(content=text), bible=bible))._score_factual(1,1,None)
    t2 = "皇帝の悲しみを HABIT bright light happy"
    p2 = "皇帝 悲しみ bright light happy focus highlight"
    out['vis_high'] = await C(make_repo(illustration=MagicMock(prompt=p2), chapter=chapter_obj(content=t2)))._score_visual_textual(1,1,None)
    t3 = "皇帝 悲しみ 物語 冬天"
    p3 = "皇帝 悲しみ 物語 冬山 風車"
    out['vis_nofocus'] = await C(make_repo(illustration=MagicMock(prompt=p3), chapter=chapter_obj(content=t3)))._score_visual_textual(1,1,None)
    t4 = "皇帝 悲しみ 物語 冬天"
    p4 = "completely different words bright happy joy"
    out['vis_low'] = await C(make_repo(illustration=MagicMock(prompt=p4), chapter=chapter_obj(content=t4)))._score_visual_textual(1,1,None)
    t5 = "彼は叫んだ！！「あああ」――"
    out['vis_textfocus'] = await C(make_repo(illustration=MagicMock(prompt=t3), chapter=chapter_obj(content=t5)))._score_visual_textual(1,1,None)
    t6 = "彼 secretly ，创造" 
    out['vis_mid'] = await C(make_repo(illustration=MagicMock(prompt="completely different words bright happy joy"), chapter=chapter_obj(content=t6)))._score_visual_textual(1,1,None)

    def sm(o, s=50,c=50,f=50,v=50,r=50):
        return MagicMock(overall_score=o, structure_score=s, coherency_score=c, factual_grounding_score=f, visual_textual_synergy_score=v, reader_experience_score=r)
    repo = make_repo(); repo.get_all_for_book.return_value = [sm(10.0,30.0), sm(20.0,40.0), sm(20.0,65.0)]
    out['pdca_full'] = await C(repo).generate_pdca_report(1)
    repo2 = make_repo(); repo2.get_all_for_book.return_value = [sm(50.0), sm(90.0), sm(55.0)]
    out['pdca_cp'] = (await C(repo2).generate_pdca_report(1))['act']['recommended_actions']
    repo3 = make_repo(); repo3.get_all_for_book.return_value = [sm(50.0,80.0,80.0,80.0,80.0,80.0), sm(50.0,80.0,80.0,80.0,80.0,80.0), sm(50.0,80.0,80.0,80.0,80.0,80.0)]
    out['pdca_none'] = await C(repo3).generate_pdca_report(1)
    repo4 = make_repo(); repo4.get_all_for_book.return_value = [sm(80.0), sm(85.0), sm(90.0)]
    out['pdca_improve'] = await C(repo4).generate_pdca_report(1)

    repo5 = make_repo(); repo5.get_all_for_book.return_value = [sm(10.0), sm(40.0), sm(70.0), sm(95.0), sm(100.0)]
    out['trend_imp'] = await C(repo5).analyze_trend(1)
    repo6 = make_repo(); repo6.get_all_for_book.return_value = [sm(50.0), sm(90.0), sm(55.0), sm(20.0)]
    out['trend_cp'] = (await C(repo6).analyze_trend(1))['changepoints']

asyncio.run(main())
def enc(o):
    if isinstance(o, dict):
        return {k: enc(v) for k, v in o.items()}
    if isinstance(o, list):
        return [enc(v) for v in o]
    return o
with io.open('tmp/probe8.json','w',encoding='utf-8') as f:
    json.dump(enc(out), f, ensure_ascii=False, indent=1)
print('ok')
