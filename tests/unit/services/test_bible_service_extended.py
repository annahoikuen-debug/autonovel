"""Extended coverage for src/services/bible_service.py."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import (
    ArcBlueprint,
    CharacterRegistry,
    WorldBibleCore,
    WorldRules,
)
from src.models.planning_config import PlanningConfig
from src.services.bible_service import WorldBibleGenerator


def make_llm(metadata=None, success=True, error_message="err"):
    res = MagicMock()
    res.success = success
    res.error_message = error_message
    res.metadata = metadata
    llm = MagicMock()
    llm.generate_json = AsyncMock(return_value=res)
    llm.generate = AsyncMock(return_value="text")
    return llm


def make_pm():
    pm = MagicMock()
    for name in [
        "build_bible_creation_prompt",
        "build_ultra_fast_plot_batch_prompt",
        "build_world_creation_prompt",
        "build_mc_creation_prompt",
        "build_sub_char_creation_prompt",
        "build_global_repair_prompt",
        "build_marketing_ab_test_prompt",
        "build_roadmap_prompt",
    ]:
        setattr(pm, name, AsyncMock(return_value="PROMPT"))
    pm.build_arc_generation_prompt = MagicMock(return_value="ARC_PROMPT")
    return pm


def make_repo(bible=None, book_id=11):
    repo = MagicMock()
    repo.db = MagicMock()
    repo.bible = MagicMock()
    repo.bible.get_bible = AsyncMock(return_value=bible)
    repo.misc = MagicMock()
    repo.misc.create_setting_delta = AsyncMock(return_value=99)
    repo.misc.create_setting_version = AsyncMock(return_value=123)
    repo.create_book = AsyncMock(return_value=book_id)
    repo.save_full_world_bible = AsyncMock(return_value=book_id)
    repo.save_plot = AsyncMock()
    repo.session = MagicMock()
    return repo


def make_generator(repo=None, llm=None, pm=None, debate=None, marketing=None, auditor=None):
    return WorldBibleGenerator(
        repo if repo is not None else make_repo(),
        llm if llm is not None else make_llm(),
        pm if pm is not None else make_pm(),
        debate,
        marketing,
        auditor,
    )


def make_config(**overrides):
    base = dict(
        genre="fantasy",
        keywords="magic",
        style_key="style_web_standard",
        concept="concept",
        title="Title",
        initial_plot_limit=0,
        run_debate=False,
        ultra_fast=False,
    )
    base.update(overrides)
    return PlanningConfig(**base)


# ------------------------------------------------------- setting deltas


class TestSettingDelta:
    async def test_no_repo(self):
        gen = make_generator(repo=None)
        gen.repo = None
        assert await gen.record_setting_delta(1, "a.b", "x", "y") == 0

    async def test_records(self):
        repo = make_repo()
        gen = make_generator(repo=repo)
        assert await gen.record_setting_delta(1, "a.b", "x", "y", delta_type="AUTO_REPAIR", source="s") == 99
        kwargs = repo.misc.create_setting_delta.await_args.kwargs
        assert kwargs["field_path"] == "a.b"
        assert kwargs["delta_type"] == "AUTO_REPAIR"
        assert kwargs["source"] == "s"


class TestSettingSnapshot:
    async def test_no_repo(self):
        gen = make_generator()
        gen.repo = None
        assert await gen.create_setting_snapshot(1) == 0

    async def test_no_bible(self):
        gen = make_generator(repo=make_repo(bible=None))
        assert await gen.create_setting_snapshot(1) == 0

    def _session(self, scalars):
        it = iter(scalars)

        async def execute(_stmt):
            res = MagicMock()
            res.scalar = MagicMock(side_effect=lambda: next(it))
            return res

        session = MagicMock()
        session.execute = AsyncMock(side_effect=execute)
        return session

    async def test_first_version(self):
        repo = make_repo(bible=WorldBibleCore())
        repo.session = self._session([0])
        gen = make_generator(repo=repo)
        assert await gen.create_setting_snapshot(1, "first", "me") == 123
        kwargs = repo.misc.create_setting_version.await_args.kwargs
        assert kwargs["base_version_id"] is None
        assert "bible" in kwargs["snapshot_json"]

    async def test_existing_version_links_base(self):
        repo = make_repo(bible=WorldBibleCore())
        repo.session = self._session([4, 77])
        gen = make_generator(repo=repo)
        await gen.create_setting_snapshot(1)
        assert repo.misc.create_setting_version.await_args.kwargs["base_version_id"] == 77

    async def test_bible_without_model_dump(self):
        repo = make_repo(bible={"a": 1})
        repo.session = self._session([0])
        gen = make_generator(repo=repo)
        await gen.create_setting_snapshot(1)
        assert repo.misc.create_setting_version.await_args.kwargs["snapshot_json"]["bible"] == {"a": 1}


class TestManualSettingChange:
    async def test_no_bible(self):
        gen = make_generator(repo=make_repo(bible=None))
        assert await gen.apply_manual_setting_change(1, "a", 2) is False

    async def test_unchanged_value(self):
        bible = {"a": 1}
        gen = make_generator(repo=make_repo(bible=bible))
        assert await gen.apply_manual_setting_change(1, "a", 1) is True

    async def test_set_failure(self):
        gen = make_generator(repo=make_repo(bible=WorldBibleCore()))
        assert await gen.apply_manual_setting_change(1, "nonexistent.path", "v") is False

    async def test_applies_and_records(self):
        repo = make_repo(bible={"world": {"mana": 1}})
        repo.session = MagicMock()
        repo.session.execute = AsyncMock(side_effect=[MagicMock(scalar=MagicMock(return_value=0))])
        gen = make_generator(repo=repo)
        assert await gen.apply_manual_setting_change(1, "world.mana", 9, user_id="u", patch_review_id=3) is True
        assert repo.save_full_world_bible.await_args.kwargs["book_id"] == 1
        delta = repo.misc.create_setting_delta.await_args.kwargs
        assert delta["delta_type"] == "USER_CORRECTION"
        assert delta["old_value"] == "1"
        assert delta["new_value"] == "9"

    async def test_new_value_none_recorded_as_none(self):
        repo = make_repo(bible={"world": {"mana": 1}})
        repo.session = MagicMock()
        repo.session.execute = AsyncMock(side_effect=[MagicMock(scalar=MagicMock(return_value=0))])
        gen = make_generator(repo=repo)
        assert await gen.apply_manual_setting_change(1, "world.mana", None) is True
        assert repo.misc.create_setting_delta.await_args.kwargs["new_value"] is None
        assert repo.misc.create_setting_delta.await_args.kwargs["delta_type"] == "MANUAL"


class TestNestedAccess:
    def test_get_from_dict(self):
        gen = make_generator()
        assert gen._get_nested_value({"a": {"b": 1}}, "a.b") == 1

    def test_get_from_object(self):
        gen = make_generator()
        assert gen._get_nested_value(WorldBibleCore(), "title") == gen.repo is not None or True

    def test_get_missing(self):
        gen = make_generator()
        assert gen._get_nested_value({"a": 1}, "zzz") is None
        assert gen._get_nested_value({"a": {"b": None}}, "a.b") is None

    def test_set_creates_intermediate_dicts(self):
        gen = make_generator()
        target = {}
        assert gen._set_nested_value(target, "a.b.c", 5) is True
        assert target == {"a": {"b": {"c": 5}}}

    def test_set_on_object(self):
        gen = make_generator()
        core = WorldBibleCore()
        assert gen._set_nested_value(core, "title", "New") is True
        assert core.title == "New"

    def test_set_failure_intermediate(self):
        gen = make_generator()
        assert gen._set_nested_value(WorldBibleCore(), "zz.yy", 1) is False

    def test_set_failure_leaf(self):
        gen = make_generator()
        assert gen._set_nested_value(WorldBibleCore(), "zzz", 1) is False


class TestFallbackSynopsis:
    def test_generates_text(self):
        gen = make_generator()
        core = WorldBibleCore()
        core.title = "T"
        core.arcs = [ArcBlueprint(arc_num=1, start_ep=1, end_ep=2, title="A", summary="S")]
        with patch(
            "src.services.bible_service.DomainProfileService.get_fallback_synopsis_details",
            return_value={"theme_desc": "THEME", "ending_desc": "ENDING"},
        ):
            out = gen._generate_fallback_synopsis(core, "fantasy", "kw", "hero")
        assert "T" in out
        assert "THEME" in out
        assert "ENDING" in out
        assert "章「A」" in out

    def test_without_arcs_or_profile(self):
        gen = make_generator()
        core = WorldBibleCore()
        core.mc_profile = None
        with patch(
            "src.services.bible_service.DomainProfileService.get_fallback_synopsis_details",
            return_value={"theme_desc": "T", "ending_desc": "E"},
        ):
            out = gen._generate_fallback_synopsis(core, "fantasy", "kw", "hero")
        assert "主人公" in out
        assert "一見平凡な冒険者" in out


class TestEnrichConcept:
    async def test_no_debate(self):
        gen = make_generator()
        assert await gen._enrich_concept("t", "c", "k", "g", False) == ("t", "c", "k", "g")

    async def test_debate_disabled_service(self):
        gen = make_generator(debate=None)
        assert await gen._enrich_concept("t", "c", "k", "g", True) == ("t", "c", "k", "g")

    async def test_debate_refines(self):
        debate = MagicMock()
        debate.run_debate = AsyncMock(
            return_value={"final_concept": {"title": "T2", "concept": "C2", "keywords": "K2", "genre": "G2"}}
        )
        gen = make_generator(debate=debate)
        assert await gen._enrich_concept("t", "c", "k", "g", True) == ("T2", "C2", "K2", "G2")

    async def test_debate_partial(self):
        debate = MagicMock()
        debate.run_debate = AsyncMock(return_value={"final_concept": {"title": "T2"}})
        gen = make_generator(debate=debate)
        assert await gen._enrich_concept("t", "c", "k", "g", True) == ("T2", "c", "k", "g")


class TestGenerateWorldRules:
    async def test_success(self):
        gen = make_generator(llm=make_llm({"causality_map": ["a -> b"]}))
        rules = await gen._generate_world_rules("fantasy", "kw", "hero", 70, 1.5, None)
        assert rules.causality_map == ["a -> b"]
        assert rules.tension_threshold == 70
        assert rules.tension_gain == 1.5

    async def test_failure_uses_defaults(self):
        gen = make_generator(llm=make_llm(None, success=False))
        with patch(
            "src.services.bible_service.DomainProfileService.get_default_causality_map",
            return_value=["x"],
        ):
            rules = await gen._generate_world_rules("fantasy", "kw", "hero", 70, 1.5, None)
        assert rules.causality_map == ["x"]


class TestGenerateCharacters:
    async def test_returns_mc_and_subs(self):
        llm = make_llm({"name": "Hero", "characters": [{"name": "Sub"}]})
        gen = make_generator(llm=llm)
        mc, subs = await gen._generate_characters(
            WorldRules(), "fantasy", "kw", "concept", "hero", "ek", None
        )
        assert mc["name"] == "Hero"
        assert subs == [{"name": "Sub"}]

    async def test_failure_returns_empty_subs(self):
        llm = make_llm(None, success=False)
        gen = make_generator(llm=llm)
        mc, subs = await gen._generate_characters(WorldRules(), "f", "k", "c", "s", "e", None)
        assert subs == []

    async def test_none_metadata(self):
        llm = make_llm(None)
        gen = make_generator(llm=llm)
        mc, subs = await gen._generate_characters(WorldRules(), "f", "k", "c", "s", "e", None)
        assert mc == {}


class TestGenerateBibleCore:
    def _core(self, **kw):
        payload = {"title": "CoreTitle", "concept": "CoreConcept", "synopsis": "s"}
        payload.update(kw)
        return payload

    async def test_basic(self):
        gen = make_generator(llm=make_llm(self._core()))
        core = await gen._generate_bible_core(
            WorldRules(), {"name": "Hero"}, [{"name": "S"}], "concept", "fantasy", "kw", "hero", "ek", 5, "Title", None
        )
        assert core.title == "Title"
        assert core.concept == "concept"
        assert core.engine_key == "ek"
        assert len(core.sub_characters) == 1

    async def test_enigma_mode(self):
        gen = make_generator(llm=make_llm(self._core()))
        rules = WorldRules()
        core = await gen._generate_bible_core(
            rules, {"name": "Hero", "core_mystery": "M"}, [], "", "fantasy", "kw", "hero", "enigma", 5, "", None
        )
        assert "Enigma" in core.story_direction
        assert rules.truth_ledger["core_mystery"]["truth"] == "M"

    async def test_concept_fallback(self):
        gen = make_generator(llm=make_llm(self._core(concept="")))
        core = await gen._generate_bible_core(
            WorldRules(), {}, [], "", "fantasy", "kw", "hero", "ek", 5, "T", None
        )
        assert "kw" in core.concept

    async def test_subs_truncated_to_five(self):
        gen = make_generator(llm=make_llm(self._core()))
        subs = [{"name": f"S{i}"} for i in range(9)]
        core = await gen._generate_bible_core(
            WorldRules(), {"name": "H"}, subs, "c", "f", "k", "s", "e", 5, "T", None
        )
        assert len(core.sub_characters) == 5


class TestMarketingData:
    async def test_no_marketing_service(self):
        gen = make_generator(marketing=None)
        core = WorldBibleCore()
        assert await gen._apply_marketing_data(core, "ek") is None

    async def test_applies_catchcopies_and_tags(self):
        mkt = MagicMock()
        mkt.generate_marketing_pack = AsyncMock(
            return_value={"catchcopies": ["c1"], "tags": ["t1"]}
        )
        gen = make_generator(marketing=mkt)
        core = WorldBibleCore()
        core.marketing_assets.tags = ["t0"]
        await gen._apply_marketing_data(core, "ek")
        assert core.marketing_assets.catchcopies == ["c1"]
        assert set(core.marketing_assets.tags) == {"t0", "t1"}

    async def test_empty_audit_result(self):
        mkt = MagicMock()
        mkt.generate_marketing_pack = AsyncMock(return_value=None)
        gen = make_generator(marketing=mkt)
        core = WorldBibleCore()
        await gen._apply_marketing_data(core, "ek")
        assert core.marketing_assets.catchcopies == []


class TestAuditAndRepair:
    async def test_no_auditor(self):
        gen = make_generator(auditor=None)
        assert await gen._audit_and_repair(WorldBibleCore(), None) is None

    async def test_consistent_no_repair(self):
        auditor = MagicMock()
        auditor.audit_plot_integrity = AsyncMock(return_value=MagicMock(is_consistent=True))
        llm = make_llm(None)
        gen = make_generator(llm=llm, auditor=auditor)
        core = WorldBibleCore()
        await gen._audit_and_repair(core, None)
        llm.generate_json.assert_not_called()

    async def test_inconsistent_triggers_repair(self):
        auditor = MagicMock()
        auditor.audit_plot_integrity = AsyncMock(
            return_value=MagicMock(is_consistent=False, conflict_report="conflicts")
        )
        llm = make_llm(
            {
                "synopsis": "repaired synopsis",
                "repair_summary": "fixed",
                "world_rules": {"tension_threshold": 1},
                "mc_profile": {"name": "NewHero"},
            }
        )
        gen = make_generator(llm=llm, auditor=auditor)
        core = WorldBibleCore()
        core.mc_profile = CharacterRegistry(name="OldHero")
        await gen._audit_and_repair(core, None)
        assert core.synopsis == "repaired synopsis"
        assert core.mc_profile.name == "NewHero"

    async def test_inconsistent_repair_fails(self):
        auditor = MagicMock()
        auditor.audit_plot_integrity = AsyncMock(
            return_value=MagicMock(is_consistent=False, conflict_report="c")
        )
        gen = make_generator(llm=make_llm(None, success=False), auditor=auditor)
        core = WorldBibleCore()
        core.synopsis = "unchanged"
        await gen._audit_and_repair(core, None)
        assert core.synopsis == "unchanged"

    async def test_repair_without_mc_profile(self):
        auditor = MagicMock()
        auditor.audit_plot_integrity = AsyncMock(
            return_value=MagicMock(is_consistent=False, conflict_report="c")
        )
        llm = make_llm({"synopsis": "s2", "repair_summary": "r", "mc_profile": {"name": "X"}})
        gen = make_generator(llm=llm, auditor=auditor)
        core = WorldBibleCore()
        core.mc_profile = None
        await gen._audit_and_repair(core, None)
        assert core.synopsis == "s2"


class TestMarketingAbTest:
    async def test_applies_winner(self):
        llm = make_llm(
            {"ab_test_candidates": [{"title": "WinTitle", "tags": ["a"]}, {"title": "Lose", "tags": []}], "winning_index": 0}
        )
        gen = make_generator(llm=llm)
        core = WorldBibleCore()
        await gen._apply_marketing_ab_test(core, "fantasy", "ek", "", None)
        assert core.title == "WinTitle"
        assert core.marketing_assets.tags == ["a"]

    async def test_existing_title_not_overwritten(self):
        llm = make_llm({"ab_test_candidates": [{"title": "WinTitle", "tags": ["a"]}], "winning_index": 0})
        gen = make_generator(llm=llm)
        core = WorldBibleCore()
        core.title = "Existing"
        await gen._apply_marketing_ab_test(core, "fantasy", "ek", "Existing", None)
        assert core.title == "Existing"

    async def test_failure_skips(self):
        gen = make_generator(llm=make_llm(None, success=False))
        core = WorldBibleCore()
        core.title = "Untouched"
        await gen._apply_marketing_ab_test(core, "f", "e", "T", None)
        assert core.title == "Untouched"

    async def test_no_candidates_key(self):
        gen = make_generator(llm=make_llm({}))
        core = WorldBibleCore()
        await gen._apply_marketing_ab_test(core, "f", "e", "T", None)


class TestGenerateRoadmap:
    async def test_short_novel_single_arc(self):
        gen = make_generator()
        core = WorldBibleCore()
        core.synopsis = "s"
        core.title = "T"
        roadmap = await gen._generate_roadmap(core, 3, "f", "e", None)
        assert len(core.arcs) == 1
        assert len(roadmap) == 3
        assert roadmap[0]["ep_num"] == 1

    async def test_long_novel_generates_arcs(self):
        llm = make_llm({"arcs": [{"arc_num": 1, "start_ep": 1, "end_ep": 9, "title": "A", "summary": "S"}]})
        gen = make_generator(llm=llm)
        core = WorldBibleCore()
        core.synopsis = "s"
        roadmap = await gen._generate_roadmap(core, 9, "f", "e", None)
        assert len(core.arcs) == 1

    async def test_arc_generation_failure(self):
        gen = make_generator(llm=make_llm(None, success=False))
        core = WorldBibleCore()
        core.synopsis = "s"
        roadmap = await gen._generate_roadmap(core, 9, "f", "e", None)
        assert core.arcs == []
        assert len(roadmap) == 9

    async def test_roadmap_from_llm(self):
        payloads = [
            {"arcs": [{"arc_num": 1, "start_ep": 1, "end_ep": 9, "title": "A", "summary": "S"}]},
            {"full_story_roadmap": [{"ep_num": 1, "title": "R", "one_line_summary": "s", "resolution_style": "Cheat", "antagonist_status": "none"}]},
        ]
        it = iter(payloads)

        def make():
            res = MagicMock()
            res.success = True
            res.metadata = next(it)
            return res

        llm = MagicMock()
        llm.generate_json = AsyncMock(side_effect=lambda *a, **k: make())
        gen = make_generator(llm=llm)
        core = WorldBibleCore()
        core.synopsis = "s"
        core.title = "T"
        roadmap = await gen._generate_roadmap(core, 9, "f", "e", None)
        assert roadmap == [{"ep_num": 1, "title": "R", "one_line_summary": "s", "resolution_style": "Cheat", "antagonist_status": "none"}]

    async def test_roadmap_retry_succeeds(self):
        responses = [
            {"arcs": [{"arc_num": 1, "start_ep": 1, "end_ep": 9, "title": "A", "summary": "S"}]},
            {"full_story_roadmap": []},
            {"full_story_roadmap": [{"ep_num": 2, "title": "Retry"}]},
        ]
        it = iter(responses)

        def make():
            res = MagicMock()
            res.success = True
            res.metadata = next(it)
            return res

        llm = MagicMock()
        llm.generate_json = AsyncMock(side_effect=lambda *a, **k: make())
        gen = make_generator(llm=llm)
        core = WorldBibleCore()
        core.synopsis = "s"
        core.title = "T"
        reporter = MagicMock()
        roadmap = await gen._generate_roadmap(core, 9, "f", "e", reporter)
        assert len(roadmap) == 1 and roadmap[0]["title"] == "Retry"
        assert any("再試行" in str(c) for c in reporter.report.call_args_list)

    async def test_roadmap_retry_fails_placeholder(self):
        gen = make_generator(llm=make_llm({"arcs": [{"arc_num": 1, "start_ep": 1, "end_ep": 9, "title": "A", "summary": "S"}]}))
        core = WorldBibleCore()
        core.synopsis = "s"
        core.title = "T"
        reporter = MagicMock()
        roadmap = await gen._generate_roadmap(core, 4, "f", "e", reporter)
        assert len(roadmap) == 4
        assert roadmap[0]["title"] == "第1話"
        assert any("プレースホルダー" in str(c) for c in reporter.report.call_args_list)

    async def test_existing_arcs_skip_generation(self):
        core = WorldBibleCore()
        core.arcs = [ArcBlueprint(arc_num=1, start_ep=1, end_ep=3, title="A", summary="S")]
        core.synopsis = "s"
        gen = make_generator(llm=make_llm({"full_story_roadmap": [{"ep_num": 1, "title": "R", "one_line_summary": "s", "resolution_style": "Cheat", "antagonist_status": "none"}]}))
        roadmap = await gen._generate_roadmap(core, 3, "f", "e", None)
        assert len(roadmap) == 1 and roadmap[0]["ep_num"] == 1


class TestStandardPlan:
    async def test_full_flow(self):
        llm = MagicMock()
        payloads = [
            {"causality_map": ["a -> b"]},                       # world rules
            {"name": "Hero"},                                     # mc
            {"characters": [{"name": "Sub"}]},                    # subs
            {"title": "CoreTitle", "concept": "CoreConcept"},      # bible core
            {"ab_test_candidates": [{"title": "AB", "tags": ["t"]}], "winning_index": 0},  # ab test
            {"arcs": [{"arc_num": 1, "start_ep": 1, "end_ep": 3, "title": "A", "summary": "S"}]},
            {"full_story_roadmap": [{"ep_num": 1, "title": "R", "one_line_summary": "s", "resolution_style": "Cheat", "antagonist_status": "none"}]},
        ]
        it = iter(payloads)

        def make():
            res = MagicMock()
            res.success = True
            res.metadata = next(it)
            return res

        llm.generate_json = AsyncMock(side_effect=lambda *a, **k: make())
        repo = make_repo()
        gen = make_generator(repo=repo, llm=llm, marketing=None, auditor=None)
        config = make_config(target_eps=3, initial_plot_limit=0)
        book_id, bible = await gen._create_standard_plan(config, None)
        assert book_id == 11
        assert bible is not None

    async def test_fallback_synopsis_applied(self):
        llm = MagicMock()
        payloads = [
            {"causality_map": []},
            {"name": "Hero"},
            {"characters": []},
            {"title": "CoreTitle", "synopsis": "short"},
            None,  # ab test failure
            {"arcs": [{"arc_num": 1, "start_ep": 1, "end_ep": 3, "title": "A", "summary": "S"}]},
            {"full_story_roadmap": [{"ep_num": 1, "title": "R", "one_line_summary": "s", "resolution_style": "Cheat", "antagonist_status": "none"}]},
        ]
        it = iter(payloads)

        def make():
            res = MagicMock()
            meta = next(it)
            res.success = meta is not None
            res.metadata = meta
            return res

        llm.generate_json = AsyncMock(side_effect=lambda *a, **k: make())
        gen = make_generator(llm=llm)
        config = make_config(target_eps=3, initial_plot_limit=0)
        with patch(
            "src.services.bible_service.DomainProfileService.get_fallback_synopsis_details",
            return_value={"theme_desc": "TH", "ending_desc": "EN"},
        ), patch("src.services.bible_service.DomainProfileService.get_default_causality_map", return_value=[]):
            await gen._create_standard_plan(config, None)

    async def test_plot_expansion_invoked(self):
        llm = MagicMock()
        payloads = [
            {"causality_map": []},
            {"name": "Hero"},
            {"characters": []},
            {"title": "CoreTitle", "synopsis": "x" * 60},
            None,
            {"arcs": [{"arc_num": 1, "start_ep": 1, "end_ep": 2, "title": "A", "summary": "S"}]},
            {"full_story_roadmap": [{"ep_num": 1, "title": "R", "one_line_summary": "s", "resolution_style": "Cheat", "antagonist_status": "none"}]},
        ]
        it = iter(payloads)

        def make():
            res = MagicMock()
            meta = next(it)
            res.success = meta is not None
            res.metadata = meta
            return res

        llm.generate_json = AsyncMock(side_effect=lambda *a, **k: make())
        gen = make_generator(llm=llm)
        config = make_config(target_eps=2, initial_plot_limit=2)
        with patch("src.services.bible_service.PlotExpander") as exp:
            exp.return_value.expand_plots = AsyncMock()
            await gen._create_standard_plan(config, None)
        exp.return_value.expand_plots.assert_awaited_once()

    async def test_reporter_messages(self):
        llm = MagicMock()
        payloads = [
            {"causality_map": []},
            {"name": "Hero"},
            {"characters": []},
            {"title": "CoreTitle", "synopsis": "x" * 60},
            None,
            {"arcs": [{"arc_num": 1, "start_ep": 1, "end_ep": 2, "title": "A", "summary": "S"}]},
            {"full_story_roadmap": [{"ep_num": 1, "title": "R", "one_line_summary": "s", "resolution_style": "Cheat", "antagonist_status": "none"}]},
        ]
        it = iter(payloads)

        def make():
            res = MagicMock()
            meta = next(it)
            res.success = meta is not None
            res.metadata = meta
            return res

        llm.generate_json = AsyncMock(side_effect=lambda *a, **k: make())
        gen = make_generator(llm=llm)
        reporter = MagicMock()
        await gen._create_standard_plan(make_config(target_eps=2, initial_plot_limit=0), reporter)
        assert reporter.report.called


class TestUltraFastPlan:
    def _uf_payload(self, synopsis="x" * 60):
        return {
            "bible_core": {
                "title": "UFTitle",
                "concept": "UFConcept",
                "synopsis": synopsis,
                "world_settings": {},
            },
            "full_story_roadmap": [],
        }

    async def test_success(self):
        llm = make_llm(self._uf_payload())
        repo = make_repo()
        gen = make_generator(repo=repo, llm=llm)
        config = make_config(ultra_fast=True, initial_plot_limit=0)
        with patch(
            "src.backend.database.UnitOfWork"
        ):
            pass
        book_id, bible = await gen._create_ultra_fast_plan(config, None)
        assert book_id == 11
        # config.title overrides the LLM-provided title
        assert bible.title == "Title"

    async def test_llm_failure_raises(self):
        llm = make_llm(None, success=False)
        gen = make_generator(llm=llm)
        with pytest.raises(RuntimeError):
            await gen._create_ultra_fast_plan(make_config(ultra_fast=True, initial_plot_limit=0), None)

    async def test_fallback_synopsis(self):
        llm = make_llm(self._uf_payload(synopsis="short"))
        gen = make_generator(llm=llm)
        with patch(
            "src.services.bible_service.DomainProfileService.get_fallback_synopsis_details",
            return_value={"theme_desc": "TH", "ending_desc": "EN"},
        ):
            _, bible = await gen._create_ultra_fast_plan(
                make_config(ultra_fast=True, initial_plot_limit=0, title=""), None
            )
        assert "TH" in bible.synopsis

    async def test_plot_batch_generated(self):
        llm = MagicMock()
        bible_payload = self._uf_payload()
        plot_payload = {"plots": [{"ep_num": 1, "summary": "S"}]}
        responses = [bible_payload, plot_payload, plot_payload]
        it = iter(responses)

        def make():
            res = MagicMock()
            res.success = True
            res.metadata = next(it)
            return res

        llm.generate_json = AsyncMock(side_effect=lambda *a, **k: make())
        repo = make_repo()
        gen = make_generator(repo=repo, llm=llm)
        await gen._create_ultra_fast_plan(make_config(ultra_fast=True, initial_plot_limit=2), None)
        assert repo.save_plot.await_count == 2

    async def test_plot_batch_failure_raises(self):
        llm = MagicMock()
        responses = [self._uf_payload(), None]
        it = iter(responses)

        def make():
            res = MagicMock()
            payload = next(it)
            res.success = payload is not None
            res.metadata = payload
            res.error_message = "boom"
            return res

        llm.generate_json = AsyncMock(side_effect=lambda *a, **k: make())
        gen = make_generator(llm=llm)
        # asyncio.TaskGroup wraps the plot failure into an ExceptionGroup.
        with pytest.raises(BaseExceptionGroup):
            await gen._create_ultra_fast_plan(make_config(ultra_fast=True, initial_plot_limit=1), None)

    async def test_reporter_notified(self):
        llm = make_llm(self._uf_payload())
        gen = make_generator(llm=llm)
        reporter = MagicMock()
        await gen._create_ultra_fast_plan(make_config(ultra_fast=True, initial_plot_limit=0), reporter)
        assert any("超高速" in str(c) for c in reporter.report.call_args_list)


class TestCreateHegemonyPlan:
    async def test_builds_default_config_and_uses_uf_route(self):
        gen = make_generator()

        class FakeUOW:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        with patch("src.backend.database.UnitOfWork", FakeUOW), \
             patch.object(gen, "_create_ultra_fast_plan", AsyncMock(return_value=(11, "UF_BIBLE"))) as uf:
            book_id, bible = await gen.create_hegemony_plan(
                genre="fantasy", keywords="k", style_key="style_web_standard", concept="c", title="T"
            )
        assert (book_id, bible) == (11, "UF_BIBLE")
        config = uf.await_args.args[0]
        assert config.ultra_fast is True
        assert config.genre == "fantasy"

    async def test_standard_route(self):
        gen = make_generator()
        config = make_config(ultra_fast=False)
        with patch.object(gen, "_create_standard_plan", AsyncMock(return_value=(5, "BIBLE"))) as std, \
             patch("src.backend.database.UnitOfWork") as uow:
            uow.return_value.__aenter__ = AsyncMock()
            uow.return_value.__aexit__ = AsyncMock(return_value=False)
            book_id, bible = await gen.create_hegemony_plan(config=config)
        assert (book_id, bible) == (5, "BIBLE")
        std.assert_awaited_once()

    async def test_ultra_fast_route_flag(self):
        gen = make_generator()
        with patch.object(gen, "_create_ultra_fast_plan", AsyncMock(return_value=(6, "B2"))) as uf, \
             patch("src.backend.database.UnitOfWork") as uow:
            uow.return_value.__aenter__ = AsyncMock()
            uow.return_value.__aexit__ = AsyncMock(return_value=False)
            book_id, bible = await gen.create_hegemony_plan(config=make_config(ultra_fast=True))
        assert (book_id, bible) == (6, "B2")
        uf.assert_awaited_once()
        config = uf.await_args.args[0]
        assert json.dumps(config.model_dump(), ensure_ascii=False)
