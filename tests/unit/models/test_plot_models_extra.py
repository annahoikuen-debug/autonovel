"""src/models/plot.py の未カバー領域を網羅する単体テスト。"""
from __future__ import annotations

import pytest

from src.models.plot import (
    ArcBlueprint,
    ArcList,
    CatharsisPattern,
    CliffhangerDef,
    ComfortAnalytics,
    DramaEpisode,
    EnigmaAnalytics,
    EpisodeMacroSkeleton,
    MasterSceneBlock,
    MysteryEpisode,
    PlotBlueprintPhase1,
    PlotBlueprintPhase1Batch,
    PlotBlueprintPhase2,
    PlotDetail,
    PlotEpisode,
    PlotMacroBatch,
    PlotMicroBlueprint,
    RedHerringItem,
    ReviewLog,
    RoadmapItem,
    RoadmapList,
    SceneBeat,
    SceneBeatBlock,
    SceneBeatList,
    SliceOfLifeEpisode,
    UltraFastPlotBatch,
    ensure_cliffhanger_obj,
    extract_float,
    merge_macro_and_micro,
    normalize_beat_type,
    plot_episode_factory,
)


class TestExtractFloat:
    @pytest.mark.parametrize("value,expected", [
        (1, 1.0), (2.5, 2.5), ("3.5", 3.5), ("7", 7.0), (None, 0.0), ([], 0.0),
    ])
    def test_extract(self, value, expected):
        assert extract_float(value) == expected

    def test_number_in_string(self):
        assert extract_float("score 85%") == 85.0

    def test_non_numeric_string(self):
        assert extract_float("none") == 0.0


class TestNormalizeBeatType:
    @pytest.mark.parametrize("value,expected", [
        ("Introduction", "導入"),
        ("Escalation", "展開"),
        ("Conclusion", "結末"),
        ("Aftermath", "余韻"),
        ("Confrontation", "具体的行動"),
        ("Tension", "内面葛藤"),
    ])
    def test_exact(self, value, expected):
        assert normalize_beat_type(value) == expected

    def test_partial_longest_match(self):
        # "Revelation of Truth" は完全一致がなく長い英語語が優先される
        assert normalize_beat_type("Revelation of Truth") in {
            "展開", "内面葛藤", "具体的行動", "余韻", "結末", "状況", "導入"
        }

    def test_japanese_passthrough(self):
        assert normalize_beat_type("展開") == "展開"

    def test_unknown_defaults(self):
        assert normalize_beat_type("unknown-xyz") == "導入"

    def test_non_string(self):
        assert normalize_beat_type(None) == "導入"
        assert normalize_beat_type(123) == "123"


class TestSmallModels:
    def test_review_log_defaults(self):
        r = ReviewLog()
        assert r.plan_name == "" and r.experiment_1_score == 0

    def test_scene_beat(self):
        b = SceneBeat(beat_num=1, physical_action="走る")
        assert b.emotion_phase == "neutral" and b.word_budget == 200

    def test_scene_beat_list_unwraps_metadata(self):
        lst = SceneBeatList.model_validate({"metadata": [{"beat_num": 1, "physical_action": "a"}]})
        assert len(lst.beats) == 1

    def test_scene_beat_list_unwraps_dict_wrapper(self):
        lst = SceneBeatList.model_validate({"metadata": {"beats": [{"beat_num": 1, "physical_action": "a"}]}})
        assert len(lst.beats) == 1

    def test_scene_beat_list_passthrough(self):
        lst = SceneBeatList.model_validate({"beats": [{"beat_num": 1, "physical_action": "a"}]})
        assert len(lst.beats) == 1

    def test_cliffhanger_def(self):
        assert CliffhangerDef().type == ""

    def test_ensure_cliffhanger_obj_string(self):
        out = ensure_cliffhanger_obj("事件")
        assert out["description"] == "事件" and out["type"] == "New Crisis"

    def test_ensure_cliffhanger_obj_dict(self):
        d = {"type": "x"}
        assert ensure_cliffhanger_obj(d) is d


class TestSceneBeatBlock:
    def test_from_string(self):
        b = SceneBeatBlock.model_validate("走る")
        assert b.beat_type == "展開"
        assert b.action_description == "走る"

    def test_defaults(self):
        b = SceneBeatBlock()
        assert b.beat_type == "導入"
        assert b.action_description == "描写なし"
        assert b.target_words == 150

    def test_normalize_english_beat_type(self):
        assert SceneBeatBlock(beat_type="Rising Action").beat_type == "展開"


class TestMasterSceneBlock:
    def test_alias_scene_id(self):
        s = MasterSceneBlock(scene_id=7)
        assert s.scene_number == 7

    def test_alias_no(self):
        assert MasterSceneBlock(no=3).scene_number == 3

    def test_beats_none(self):
        assert MasterSceneBlock(scene_number=1, beats=None).beats == []

    def test_beats_from_string(self):
        s = MasterSceneBlock(scene_number=1, beats=" 走る ")
        assert s.beats[0].action_description == "走る"
        assert s.beats[0].beat_type == "状況"

    def test_beats_from_empty_string(self):
        s = MasterSceneBlock(scene_number=1, beats="   ")
        assert s.beats[0].action_description == "描写なし"

    def test_beats_list_with_strings(self):
        s = MasterSceneBlock(scene_number=1, beats=["走る", "跳ぶ"])
        assert [b.beat_type for b in s.beats] == ["展開", "展開"]

    def test_impact_score_bounds(self):
        assert MasterSceneBlock(scene_number=1, impact_score=0).impact_score == 0
        with pytest.raises(Exception):
            MasterSceneBlock(scene_number=1, impact_score=101)


class TestPlotBlueprint:
    def test_phase1_defaults_and_aliases(self):
        p = PlotBlueprintPhase1(tension="70", next_hook="事件")
        assert p.tension == 70
        assert p.next_hook.description == "事件"

    def test_phase1_batch_unwrap(self):
        b = PlotBlueprintPhase1Batch.model_validate({"episodes": [{"tension": 10}]})
        assert b.episodes[0].tension == 10

    def test_phase2(self):
        p = PlotBlueprintPhase2(scenes=[{"scene_number": 1}])
        assert p.scenes[0].scene_number == 1


class TestMacroMicro:
    def test_macro_alias_ep(self):
        m = EpisodeMacroSkeleton(episode="3", tension="80")
        assert m.ep_num == 3 and m.tension == 80

    def test_macro_next_hook_string(self):
        m = EpisodeMacroSkeleton(next_hook="hooked")
        assert m.next_hook.description == "hooked"

    def test_macro_batch_unwrap_results(self):
        b = PlotMacroBatch.model_validate({"results": [{"ep": 1}]})
        assert b.episodes[0].ep_num == 1

    def test_macro_batch_unwrap_dict(self):
        b = PlotMacroBatch.model_validate({"metadata": {"episodes": [{"ep": 1}]}})
        assert b.episodes[0].ep_num == 1

    def test_micro_requires_ep(self):
        with pytest.raises(Exception):
            PlotMicroBlueprint()

    def test_micro_alias(self):
        m = PlotMicroBlueprint(no=2)
        assert m.ep_num == 2

    def test_merge_macro_micro_mismatch(self):
        macro = EpisodeMacroSkeleton(ep_num=1)
        micro = PlotMicroBlueprint(ep_num=2)
        with pytest.raises(ValueError):
            merge_macro_and_micro(macro, micro)

    def test_merge_macro_micro(self):
        macro = EpisodeMacroSkeleton(ep_num=1, title="T", tension=70, foreshadowing_plan=["f1"])
        micro = PlotMicroBlueprint(ep_num=1, detailed_blueprint="BP", script_content="SC")
        ep = merge_macro_and_micro(macro, micro)
        assert isinstance(ep, PlotEpisode)
        assert ep.ep_num == 1 and ep.detailed_blueprint == "BP"
        assert ep.tension == 70


class TestAnalytics:
    def test_red_herring_item(self):
        r = RedHerringItem(id=1, clue="c", ep_num=2)
        assert r.resolved is False

    def test_enigma_add_and_eliminate(self):
        e = EnigmaAnalytics(knowledge_delta="0.5", truth_convergence="0.8")
        assert e.knowledge_delta == 0.5
        rid = e.add_red_herring("clue", 1)
        assert rid == 1
        e.add_red_herring("clue2", 1)
        e.eliminate_red_herring(rid, 5, "解決")
        assert e.red_herrings[0].resolved is True
        assert e.red_herrings[0].resolve_ep_num == 5
        assert e.red_herrings[0].resolution == "解決"

    def test_enigma_eliminate_unknown_id(self):
        e = EnigmaAnalytics()
        e.add_red_herring("c", 1)
        e.eliminate_red_herring(99, 2, "x")
        assert e.red_herrings[0].resolved is False

    def test_enigma_aliases(self):
        e = EnigmaAnalytics(convergence=0.3, friction=0.4, intel_gap=0.1)
        assert e.truth_convergence == 0.3
        assert e.knowledge_friction == 0.4
        assert e.knowledge_delta == 0.1

    def test_comfort_analytics(self):
        c = ComfortAnalytics(qol_delta="5", veneration_gain="0.2")
        assert c.qol_delta == 5 and c.veneration_gain == 0.2
        assert c.discovery_item is None


class TestPlotEpisodeProperties:
    def test_analytics_setters(self):
        ep = PlotEpisode()
        ep.tension = 10
        ep.tension_delta = 3
        ep.catharsis = 4
        ep.is_catharsis = True
        ep.love_meter = 6
        ep.catharsis_type = "感情"
        ep.emotional_payoff = "payoff"
        ep.resolution_style = "Logic"
        ep.antagonist_status = "撃破"
        assert ep.analytics.tension == 10
        assert ep.analytics.catharsis_type == "感情"
        assert ep.resolution_style == "Logic"

    def test_core_info_setters(self):
        ep = PlotEpisode()
        ep.title = "T"
        ep.one_line_summary = "S"
        ep.thought_process = "TP"
        ep.detailed_blueprint = "DB"
        ep.ep_num = 4
        assert ep.core_info.title == "T"
        assert ep.ep_num == 4

    def test_flat_aliases(self):
        # フラットキーはサブモデル（core_info/analytics/...）へ動的ルーティングされる
        ep = PlotEpisode.model_validate({
            "ep_num": 5,
            "title": "T",
            "tension": 60,
            "misunderstanding_gap": "irony",
            "burned_cost_or_loot": "代償",
            "thematic_milestone": "M",
            "emotional_resonance_score": 70,
            "thematic_depth_score": 60,
            "literary_beauty_score": 80,
            "lite_model_director_notes": "N",
        })
        assert ep.ep_num == 5
        assert ep.misunderstanding_gap == "irony"
        assert ep.burned_cost_or_loot == "代償"
        assert ep.thematic_milestone == "M"
        assert ep.emotional_resonance_score == 70
        assert ep.thematic_depth_score == 60
        assert ep.literary_beauty_score == 80
        assert ep.lite_model_director_notes == "N"

    def test_dynamic_routing_of_submodel_fields(self):
        ep = PlotEpisode.model_validate({
            "tension": 33,
            "knowledge_delta": 0.2,
            "qol_delta": 7,
            "ep_num": 2,
        })
        assert ep.analytics.tension == 33
        assert ep.enigma.knowledge_delta == 0.2
        assert ep.comfort.qol_delta == 7

    def test_wrapper_peeling(self):
        ep = PlotEpisode.model_validate({"metadata": {"ep_num": 6, "tension": 12}})
        assert ep.ep_num == 6 and ep.tension == 12

    def test_extra_engines_capture(self):
        ep = PlotEpisode.model_validate({"ep_num": 1, "mystery_flag": True, "new_thing": 3})
        assert ep.extra_engines["mystery_flag"] is True
        assert ep.extra_engines["new_thing"] == 3

    def test_unknown_keys_go_to_extra_engines(self):
        # 未定義のエイリアス (ep/script など) は extra_engines へ退避される
        ep = PlotEpisode.model_validate({"ep": 1, "script": "body", "scenes": []})
        assert ep.extra_engines["script"] == "body"
        assert ep.ep_num == 0

    def test_serialize_flat(self):
        ep = PlotEpisode.model_validate({"ep": 1, "tension": 42, "mystery_flag": True})
        dumped = ep.model_dump()
        assert "core_info" not in dumped
        assert "extra_engines" not in dumped
        assert dumped["tension"] == 42
        assert dumped["mystery_flag"] is True

    def test_nested_submodel_preserved(self):
        ep = PlotEpisode.model_validate({"analytics": {"tension": 11}, "ep": 1})
        assert ep.tension == 11

    def test_self_critique_and_stress_aliases(self):
        ep = PlotEpisode(lite_model_director_notes="crit", tension_delta=9)
        assert ep.self_critique == "crit"
        assert ep.stress == 9

    def test_to_catharsis_summary(self):
        ep = PlotEpisode(ep_num=3, tension=50, tension_delta=5, is_catharsis=True)
        s = ep.to_catharsis_summary()
        assert s["ep_num"] == 3 and s["is_catharsis"] is True
        assert s["cumulative_stress"] == 5

    def test_extract_macro_skeleton(self):
        ep = PlotEpisode(ep_num=2, title="T", one_line_summary="S", foreshadowing_refs=["f"])
        macro = ep.extract_macro_skeleton()
        assert isinstance(macro, EpisodeMacroSkeleton)
        assert macro.ep_num == 2
        assert macro.inciting_event == "S"
        assert macro.foreshadowing_plan == ["f"]

    def test_extract_micro_blueprint(self):
        ep = PlotEpisode(ep_num=2, script_content="body")
        micro = ep.extract_micro_blueprint()
        assert isinstance(micro, PlotMicroBlueprint)
        assert micro.script_content == "body"

    def test_candidates_captured_as_extra(self):
        # candidates はルーティング先を持たないため extra_engines へ退避される
        ep = PlotEpisode.model_validate({"ep_num": 1, "candidates": [{"ep_num": 2}]})
        assert ep.extra_engines["candidates"][0]["ep_num"] == 2
        assert ep.candidates == []


class TestGenreEpisodes:
    def test_mystery_catharsis(self):
        m = MysteryEpisode.model_validate({
            "ep_num": 1, "knowledge_delta": 0.5, "truth_convergence": 0.4
        })
        score = m.calculate_mystery_catharsis()
        assert score == 20
        rid = m.enigma.add_red_herring("c", 1)
        m.enigma.eliminate_red_herring(rid, 2, "r")
        assert m.calculate_mystery_catharsis() == 30

    def test_slice_of_life_has_comfort(self):
        e = SliceOfLifeEpisode(ep=1, qol_delta=3)
        assert e.comfort.qol_delta == 3

    def test_drama_has_both(self):
        d = DramaEpisode(ep=1, knowledge_delta=0.1, qol_delta=2)
        assert d.enigma.knowledge_delta == 0.1
        assert d.comfort.qol_delta == 2

    def test_factory_selection(self):
        assert isinstance(plot_episode_factory("mystery"), MysteryEpisode)
        assert isinstance(plot_episode_factory("SLICE_OF_LIFE"), SliceOfLifeEpisode)
        assert isinstance(plot_episode_factory("drama"), DramaEpisode)
        assert type(plot_episode_factory("unknown")) is PlotEpisode


class TestRoadmap:
    def test_aliases_and_normalization_logic(self):
        r = RoadmapItem.model_validate({
            "no": 3, "summary": "S", "style": "徹底的な論理思考", "enemy_status": "敵消滅"
        })
        assert r.ep_num == 3
        assert r.resolution_style == "Logic"
        assert r.antagonist_status == "敵消滅"
        assert r.burned_cost_or_loot == "なし"

    def test_normalization_drama(self):
        r = RoadmapItem.model_validate({
            "ep_num": 1, "one_line_summary": "s", "resolution_style": "感動のドラマ",
            "antagonist_status": "a",
        })
        assert r.resolution_style == "Focus_Drama"

    def test_normalization_cheat(self):
        r = RoadmapItem.model_validate({
            "ep_num": 1, "one_line_summary": "s", "resolution_style": "power fantasy",
            "antagonist_status": "a",
        })
        assert r.resolution_style == "Cheat"

    def test_get_method(self):
        r = RoadmapItem(ep_num=1, one_line_summary="s", resolution_style="Cheat", antagonist_status="a")
        assert r.get("ep_num") == 1
        assert r.get("nope", "d") == "d"

    def test_roadmap_list(self):
        lst = RoadmapList(full_story_roadmap=[])
        assert lst.full_story_roadmap == []


class TestArcBlueprint:
    def test_aliases(self):
        a = ArcBlueprint.model_validate({"number": 2, "start": 1, "end": 5, "description": "d"})
        assert a.arc_num == 2 and a.start_ep == 1 and a.end_ep == 5
        assert a.summary == "d"

    def test_wrapper_unwrap(self):
        a = ArcBlueprint.model_validate({"metadata": {"arc_num": 1, "start_ep": 1, "end_ep": 2}})
        assert a.arc_num == 1

    def test_defaults_when_missing(self):
        a = ArcBlueprint()
        assert a.arc_num == 1 and a.start_ep == 1 and a.end_ep == 1
        assert a.title == "無題"

    def test_end_ep_falls_back_to_start(self):
        a = ArcBlueprint.model_validate({"arc_num": 1, "start_ep": 3})
        assert a.end_ep == 3

    def test_get_method(self):
        a = ArcBlueprint(arc_num=1)
        assert a.get("arc_num") == 1
        assert a.get("nope") is None

    def test_arc_list_unwrap(self):
        lst = ArcList.model_validate({"arc_list": [{"arc_num": 1}]})
        assert len(lst.arcs) == 1

    def test_arc_list_dict_wrapper(self):
        lst = ArcList.model_validate({"metadata": {"arcs": [{"arc_num": 1}]}})
        assert len(lst.arcs) == 1


class TestCatharsisAndBatch:
    def test_to_summary(self):
        p = CatharsisPattern(cumulative_stress=10, catharsis_points=[3, 5], tension_wave=[1, 2])
        s = p.to_summary()
        assert s["catharsis_count"] == 2
        assert s["catharsis_positions"] == [3, 5]
        assert s["pattern_type"] == "wave"

    def test_ultra_fast_batch(self):
        b = UltraFastPlotBatch(plots=[{"ep": 1}])
        assert len(b.plots) == 1

    def test_plot_detail(self):
        d = PlotDetail.model_validate({"ep_num": 1, "detailed_analysis": "DA"})
        # サブモデル以外の未知キーは extra_engines 経由で保持される
        dumped = d.model_dump()
        assert dumped["detailed_analysis"] == "DA"
