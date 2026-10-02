"""逆プロット系が STORY_SPINE を土台にしていることの確認。"""

from src.backend.workflows.reverse_plot_workflow import ReversePlotGenerationWorkflow

ANSWERS = {
    "coreConflict": "ideal_vs_reality",
    "emotionalGoal": "triumph",
    "sacrifice": "peace",
    "openingHook": "isekai_awakening",
}


def test_calc_tension_removed():
    """`Spine` と二重実装された tension 計算が消えていること。"""
    from pathlib import Path

    src = Path("src/backend/workflows/reverse_plot_workflow.py").read_text(encoding="utf-8")
    assert "def _calc_tension" not in src, "_calc_tension が復活している"


def test_spine_is_the_single_source_of_tension():
    """各話の tension が Spine の値と一致すること。"""
    from src.services.spine_resolver import resolve_spine

    w = ReversePlotGenerationWorkflow()
    eps = 40
    spine = resolve_spine("exile_rise", "web_volume", "web", eps)
    episodes = w._design_episodes(ANSWERS, w._design_arcs(ANSWERS, eps), eps, "ファンタジー")
    for e in episodes:
        beat = spine.at(e.ep_num)
        assert e.tension == round(beat.tension * 100), (
            f"第{e.ep_num}話の tension {e.tension} が Spine と一致しない"
        )


def test_opening_hook_is_actually_used():
    """`openingHook` 回答が第1話に反映されていること（旧実装は無視していた）。"""
    w = ReversePlotGenerationWorkflow()
    eps = 10
    episodes = w._design_episodes(ANSWERS, w._design_arcs(ANSWERS, eps), eps, "ファンタジー")
    assert ANSWERS["openingHook"] in episodes[0].one_line_summary


def test_sacrifice_is_used_at_the_final_episode():
    w = ReversePlotGenerationWorkflow()
    eps = 12
    episodes = w._design_episodes(ANSWERS, w._design_arcs(ANSWERS, eps), eps, "ファンタジー")
    assert episodes[-1].burned_cost_or_loot == ANSWERS["sacrifice"]
    assert episodes[0].burned_cost_or_loot != ANSWERS["sacrifice"]


def test_beat_label_appears_in_summary():
    """各話サマリーに Spine の beat 名が入っていること（同一文の繰り返しをやめた）。"""
    w = ReversePlotGenerationWorkflow()
    eps = 20
    episodes = w._design_episodes(ANSWERS, w._design_arcs(ANSWERS, eps), eps, "ファンタジー")
    summaries = {e.one_line_summary for e in episodes}
    assert len(summaries) >= 5, f"サマリーが {len(summaries)} 種類しかない（重複しすぎ）"


def test_arc_count_comes_from_length_profile():
    """部の区切りが LENGTH_PROFILE に従うこと。"""
    w = ReversePlotGenerationWorkflow()
    arcs = w._design_arcs(ANSWERS, 40)
    assert arcs, "部が1つも無い"
    assert arcs[0].start_ep == 1
    assert arcs[-1].end_ep == 40
    assert all(a.end_ep < arcs[i + 1].start_ep for i, a in enumerate(arcs[:-1])), "部の区切りが重複"


def test_catharsis_wave_length_matches_episodes():
    w = ReversePlotGenerationWorkflow()
    eps = 30
    cath = w._design_catharsis(ANSWERS, eps)
    assert len(cath.tension_wave) == eps
    assert all(0 <= t <= 100 for t in cath.tension_wave)


def test_spine_resolution_makes_no_llm_call():
    """逆プロットでも構造解決は LLM 0 回であること。"""
    from pathlib import Path

    src = Path("src/backend/workflows/reverse_plot_workflow.py").read_text(encoding="utf-8")
    for forbidden in ("ResilientLLMGateway", "invoke_llm", "call_llm"):
        assert forbidden not in src, f"{forbidden} が混入している"
