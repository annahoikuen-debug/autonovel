"""`DefaultPlotExpander` の spine フック回帰テスト。

壊れ方: resolve_spine 例外で執筆が落ちる（fail-closed 化）/
        pattern_key 未保存書籍で KeyError /
        off でもプロンプトに構造指示が混入する → この回帰が赤になる。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from config.story_spine import resolve_spine
from src.engine.default_plot_expander import DefaultPlotExpander
from src.models.plot import EpisodeMacroSkeleton, PlotMicroBlueprint


class _FakeRepo:
    """get_latest_bible / get_all_characters / get_plot / create_or_replace_plot をモック化。"""

    def __init__(self, bible_dict=None, chars=None):
        self.bible_dict = bible_dict or {}
        self.chars = chars or []
        self.created_plots = []

    async def get_latest_bible(self, book_id):
        if self.bible_dict is None:
            return None
        return self.bible_dict

    async def get_all_characters(self, book_id):
        return self.chars

    async def get_plot(self, branch_id, ep_num, book_id=None):
        return None

    async def create_or_replace_plot(self, book_id, ep_num, plot):
        self.created_plots.append((book_id, ep_num, plot))


class _FakeLLM:
    def __init__(self, ep_num=1):
        self.ep_num = ep_num
        self.calls = []

    async def generate_json(self, model, prompt, response_schema, reporter=None):
        self.calls.append((model, prompt, response_schema))
        return PlotMicroBlueprint(ep_num=self.ep_num)


class _FakePM:
    """build_micro_scene_expander_prompt / build_macro_plot_skeleton_prompt の呼び出し引数を記録。"""

    def __init__(self):
        self.calls = []

    async def build_micro_scene_expander_prompt(
        self, macro_skeleton, previous_ending_text="", characters_summary="",
        book_id=None, spine=None, spine_quality=None,
    ):
        self.calls.append(
            dict(
                ep_num=getattr(macro_skeleton, "ep_num", None),
                spine=spine,
                spine_quality=spine_quality,
                previous_ending_text=previous_ending_text,
                characters_summary=characters_summary,
                book_id=book_id,
            )
        )
        return "micro prompt"

    async def build_macro_plot_skeleton_prompt(
        self, bible_json_str, ep_range, book_id=None, spine=None, spine_quality=None,
    ):
        self.calls.append(
            dict(ep_range=ep_range, spine=spine, spine_quality=spine_quality, book_id=book_id)
        )
        return "macro prompt"


class _FakeReporter:
    def report(self, msg, level="info"):
        pass


@pytest.fixture
def skeleton():
    return EpisodeMacroSkeleton(
        ep_num=3,
        title="第3話",
        one_line_summary="主人公が試練に挑む",
        inciting_event="試練の提示",
        climax_payoff="克服",
        tension=60,
        current_chain_phase="Conflict",
        resolution_style="Cheat",
        foreshadowing_plan=[],
    )


@pytest.mark.asyncio
async def test_no_pattern_key_uses_default_and_resolves_spine(skeleton):
    """bible に pattern_key がないとき、コンストラクタのデフォルト値（exile_rise）を
    使用して spine が解決されること。"""
    repo = _FakeRepo(bible_dict={})  # pattern_key なし
    pm = _FakePM()
    llm = _FakeLLM(ep_num=3)
    expander = DefaultPlotExpander(repo=repo, pm=pm, llm=llm)

    await expander.expand_single_micro(book_id=1, ep_num=3, skeleton=skeleton, reporter=_FakeReporter())

    assert len(pm.calls) == 1
    call = pm.calls[0]
    assert call["spine"] is not None, "spine が解決されていない（デフォルト値が使われていない）"
    assert call["spine_quality"] == "off", "既定の spine_quality は off であること"


@pytest.mark.asyncio
async def test_pattern_key_from_bible_is_used(skeleton):
    """bible に pattern_key が保存されているとき、それを優先して使用すること。"""
    repo = _FakeRepo(bible_dict={"pattern_key": "detective_mystery", "length_key": "short", "market_key": "general"})
    pm = _FakePM()
    llm = _FakeLLM(ep_num=3)
    expander = DefaultPlotExpander(repo=repo, pm=pm, llm=llm)

    await expander.expand_single_micro(book_id=1, ep_num=3, skeleton=skeleton, reporter=_FakeReporter())

    call = pm.calls[0]
    assert call["spine"] is not None
    # detective_mystery × short × general の spine が解決される
    expected = resolve_spine("detective_mystery", "short", "general", 100)
    assert call["spine"].keys == expected.keys


@pytest.mark.asyncio
async def test_resolve_spine_exception_falls_back_to_none(skeleton, monkeypatch):
    """resolve_spine が例外を投げても None にフォールバックし、執筆パイプラインが継続すること
    （fail-open、H5 の契約）。"""

    def _boom(*args, **kwargs):
        raise RuntimeError("spine resolution failed")

    import src.engine.default_plot_expander as expander_mod

    monkeypatch.setattr(expander_mod, "resolve_spine", _boom)

    repo = _FakeRepo(bible_dict={})
    pm = _FakePM()
    llm = _FakeLLM(ep_num=3)
    expander = DefaultPlotExpander(repo=repo, pm=pm, llm=llm)

    result = await expander.expand_single_micro(
        book_id=1, ep_num=3, skeleton=skeleton, reporter=_FakeReporter()
    )

    # 執筆が継続し、PlotEpisode が返される
    assert result is not None
    assert result.ep_num == 3
    # pm には spine=None が渡される（fail-open）
    assert pm.calls[0]["spine"] is None


@pytest.mark.asyncio
async def test_macro_skeleton_passes_spine_to_prompt_builder(skeleton):
    """expand_macro_skeletons でも spine が解決され、build_macro_plot_skeleton_prompt に渡されること。"""
    from unittest.mock import AsyncMock as _AM
    from src.models.plot import PlotMacroBatch

    repo = _FakeRepo(bible_dict={})
    pm = _FakePM()
    llm = _FakeLLM(ep_num=1)
    llm.generate_json = _AM(return_value=PlotMacroBatch(episodes=[skeleton]))

    expander = DefaultPlotExpander(repo=repo, pm=pm, llm=llm)

    await expander.expand_macro_skeletons(book_id=1, target_ep_list=[1], reporter=_FakeReporter())

    macro_calls = [c for c in pm.calls if "ep_range" in c]
    assert len(macro_calls) == 1, "build_macro_plot_skeleton_prompt が呼ばれていない"
    assert macro_calls[0]["spine"] is not None, "macro に spine が渡されていない"
    assert macro_calls[0]["spine_quality"] == "off", "macro の spine_quality は off であること"


@pytest.mark.asyncio
async def test_spine_resolution_is_deterministic(skeleton):
    """同一書籍で expand を 2 回呼んでも、注入される構造指示が同一であること（決定論）。"""
    repo = _FakeRepo(bible_dict={})
    pm = _FakePM()
    llm = _FakeLLM(ep_num=3)
    expander = DefaultPlotExpander(repo=repo, pm=pm, llm=llm)

    await expander.expand_single_micro(book_id=1, ep_num=3, skeleton=skeleton, reporter=_FakeReporter())
    call1 = pm.calls[0]["spine"]
    pm.calls.clear()

    await expander.expand_single_micro(book_id=1, ep_num=3, skeleton=skeleton, reporter=_FakeReporter())
    call2 = pm.calls[0]["spine"]

    assert call1.keys == call2.keys
    assert call1.at(3).duty == call2.at(3).duty
