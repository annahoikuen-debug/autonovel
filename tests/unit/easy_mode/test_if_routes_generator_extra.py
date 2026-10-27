"""IFルート生成器・プレイヤーの追加単体テスト."""

from src.easy_mode import EpisodeResult, SeriesResult
from src.easy_mode.phase3.if_routes import (
    BranchCondition,
    BranchType,
    ConditionOperator,
    IFRouteGenerator,
    IFRouteGraph,
    IFRoutePlayer,
    RouteChoice,
    RouteNode,
    create_if_route_system,
)


def make_episode(num: int = 1, content: str = "本文", metadata: dict | None = None) -> EpisodeResult:
    return EpisodeResult(
        episode_num=num,
        title=f"第{num}話",
        content=content,
        word_count=len(content),
        audit_score=80.0,
        audit_passed=True,
        rewrite_count=0,
        spice_elements=[],
        metadata=metadata or {},
    )


def make_series(n: int = 3, genre: str = "fantasy", metadata: dict | None = None) -> SeriesResult:
    return SeriesResult(
        genre=genre,
        title="物語",
        concept="c",
        total_episodes=n,
        episodes=[make_episode(i + 1, f"本文{i + 1}", {"plot": {"is_catharsis": i == 1}}) for i in range(n)],
        bible={},
        plot_outline=[],
        metadata=metadata if metadata is not None else {},
    )


class TestBranchCondition:
    def test_evaluate_nested(self):
        c = BranchCondition("flags.x", ConditionOperator.EQUALS, True)
        assert c.evaluate({"flags": {"x": True}}) is True
        assert c.evaluate({"flags": {"x": False}}) is False

    def test_evaluate_missing(self):
        c = BranchCondition("a.b", ConditionOperator.EQUALS, 1)
        assert c.evaluate({}) is False

    def test_evaluate_non_dict_mid(self):
        c = BranchCondition("a.b", ConditionOperator.EQUALS, 1)
        assert c.evaluate({"a": 5}) is False

    def test_evaluate_operators(self):
        ctx = {"n": 5, "s": "hello"}
        assert BranchCondition("n", ConditionOperator.EQUALS, 5).evaluate(ctx)
        assert BranchCondition("n", ConditionOperator.NOT_EQUALS, 4).evaluate(ctx)
        assert BranchCondition("n", ConditionOperator.GREATER_THAN, 4).evaluate(ctx)
        assert BranchCondition("n", ConditionOperator.LESS_THAN, 6).evaluate(ctx)
        assert BranchCondition("n", ConditionOperator.GREATER_EQUAL, 5).evaluate(ctx)
        assert BranchCondition("n", ConditionOperator.LESS_EQUAL, 5).evaluate(ctx)
        assert BranchCondition("s", ConditionOperator.CONTAINS, "ell").evaluate(ctx)
        assert BranchCondition("s", ConditionOperator.NOT_CONTAINS, "zzz").evaluate(ctx)

    def test_evaluate_unknown_operator(self):
        cond = BranchCondition("n", "nope", 1)
        assert cond.evaluate({"n": 1}) is False

    def test_roundtrip_dict(self):
        c = BranchCondition("n", ConditionOperator.EQUALS, 1, "desc")
        d = c.to_dict()
        assert d["operator"] == "eq"
        back = BranchCondition.from_dict(d)
        assert back.description == "desc"

    def test_from_dict_no_description(self):
        c = BranchCondition.from_dict({"variable": "n", "operator": "ne", "value": 1})
        assert c.description == ""


class TestRouteChoice:
    def test_is_available_no_conditions(self):
        assert RouteChoice(id="a", text="t").is_available({}) is True

    def test_is_available_with_conditions(self):
        c = RouteChoice(
            id="a",
            text="t",
            conditions=[BranchCondition("f", ConditionOperator.EQUALS, True)],
        )
        assert c.is_available({"f": True}) is True
        assert c.is_available({"f": False}) is False

    def test_apply_effects_deep_copy(self):
        c = RouteChoice(id="a", text="t", effects={"flags.x": 1})
        ctx = {"flags": {}}
        new = c.apply_effects(ctx)
        assert new["flags"]["x"] == 1
        assert ctx["flags"] == {}

    def test_apply_effects_existing_nested(self):
        c = RouteChoice(id="a", text="t", effects={"a.b": 2})
        new = c.apply_effects({"a": {"b": 1, "c": 3}})
        assert new["a"] == {"b": 2, "c": 3}


class TestRouteNode:
    def test_get_available_choices(self):
        node = RouteNode(
            id="n",
            episode_num=1,
            content="c",
            branch_type=BranchType.CHOICE,
            choices=[
                RouteChoice(id="a", text="t"),
                RouteChoice(
                    id="b",
                    text="t",
                    conditions=[BranchCondition("f", ConditionOperator.EQUALS, True)],
                ),
            ],
        )
        assert len(node.get_available_choices({"f": True})) == 2
        assert len(node.get_available_choices({})) == 1

    def test_to_dict_and_from_dict(self):
        node = RouteNode(
            id="n",
            episode_num="3",
            content="c",
            branch_type=BranchType.MERGE,
            choices=[
                RouteChoice(
                    id="a",
                    text="t",
                    conditions=[BranchCondition("f", ConditionOperator.EQUALS, True)],
                )
            ],
            merge_target="m",
            metadata={"a": 1},
            parent_ids=["p"],
        )
        d = node.to_dict()
        assert d["branch_type"] == "merge"
        restored = RouteNode.from_dict(d)
        assert restored.episode_num == 3
        assert restored.merge_target == "m"
        assert restored.parent_ids == ["p"]

    def test_from_dict_invalid_branch_type(self):
        node = RouteNode.from_dict({"id": "n", "branch_type": "unknown"})
        assert node.branch_type == BranchType.CHOICE
        assert node.choices == []
        assert node.metadata == {}
        assert node.parent_ids == []


class TestIFRouteGraph:
    def test_add_and_get(self):
        g = IFRouteGraph()
        node = RouteNode(id="a", episode_num=1, content="c", branch_type=BranchType.CHOICE)
        g.add_node(node)
        assert g.get_node("a") is node
        assert g.get_node("zzz") is None

    def test_add_edge(self):
        g = IFRouteGraph()
        g.add_edge("a", "b", "choice")
        assert g.edges == [("a", "b", "choice")]

    def test_get_next_nodes(self):
        g = IFRouteGraph()
        a = RouteNode(
            id="a",
            episode_num=1,
            content="",
            branch_type=BranchType.CHOICE,
            choices=[RouteChoice(id="c1", text="t", target_node_id="b")],
        )
        b = RouteNode(id="b", episode_num=2, content="", branch_type=BranchType.MERGE, merge_target="c")
        c = RouteNode(id="c", episode_num=3, content="", branch_type=BranchType.MERGE)
        for n in (a, b, c):
            g.add_node(n)
        assert [n.id for n in g.get_next_nodes("a", {})] == ["b"]
        assert [n.id for n in g.get_next_nodes("b", {})] == ["c"]
        assert [n.id for n in g.get_next_nodes("missing", {})] == []

    def test_get_next_nodes_merge_missing(self):
        g = IFRouteGraph()
        g.add_node(
            RouteNode(
                id="a", episode_num=1, content="", branch_type=BranchType.MERGE, merge_target="zzz"
            )
        )
        assert g.get_next_nodes("a", {}) == []

    def test_get_next_nodes_filters_conditions(self):
        g = IFRouteGraph()
        g.add_node(
            RouteNode(
                id="a",
                episode_num=1,
                content="",
                branch_type=BranchType.CHOICE,
                choices=[
                    RouteChoice(
                        id="c",
                        text="t",
                        target_node_id="b",
                        conditions=[BranchCondition("f", ConditionOperator.EQUALS, True)],
                    )
                ],
            )
        )
        g.add_node(RouteNode(id="b", episode_num=2, content="", branch_type=BranchType.CHOICE))
        assert g.get_next_nodes("a", {}) == []

    def test_validate_ok(self):
        g = IFRouteGraph(entry_node_id="a")
        g.add_node(
            RouteNode(
                id="a",
                episode_num=1,
                content="",
                branch_type=BranchType.CHOICE,
                choices=[RouteChoice(id="c", text="t", target_node_id="b")],
            )
        )
        g.add_node(RouteNode(id="b", episode_num=2, content="", branch_type=BranchType.MERGE))
        assert g.validate() == []

    def test_validate_entry_missing(self):
        g = IFRouteGraph(entry_node_id="zzz")
        assert any("Entry node" in e for e in g.validate())

    def test_validate_unreachable(self):
        g = IFRouteGraph(entry_node_id="a")
        g.add_node(RouteNode(id="a", episode_num=1, content="", branch_type=BranchType.CHOICE))
        g.add_node(RouteNode(id="iso", episode_num=2, content="", branch_type=BranchType.CHOICE))
        assert any("Unreachable node: iso" in e for e in g.validate())

    def test_validate_missing_target(self):
        g = IFRouteGraph(entry_node_id="a")
        g.add_node(
            RouteNode(
                id="a",
                episode_num=1,
                content="",
                branch_type=BranchType.CHOICE,
                choices=[RouteChoice(id="c", text="t", target_node_id="ghost")],
            )
        )
        assert any("targets missing node ghost" in e for e in g.validate())

    def test_validate_traverse_merge_target(self):
        g = IFRouteGraph(entry_node_id="a")
        g.add_node(
            RouteNode(id="a", episode_num=1, content="", branch_type=BranchType.MERGE, merge_target="m")
        )
        g.add_node(RouteNode(id="m", episode_num=2, content="", branch_type=BranchType.CHOICE))
        g.add_node(RouteNode(id="b", episode_num=3, content="", branch_type=BranchType.CHOICE))
        errors = g.validate()
        assert any("Unreachable node: b" in e for e in errors)

    def test_to_dict_from_dict(self):
        g = IFRouteGraph(entry_node_id="a", metadata={"genre": "loop"})
        g.add_node(
            RouteNode(
                id="a",
                episode_num=1,
                content="c",
                branch_type=BranchType.CHOICE,
                choices=[
                    RouteChoice(
                        id="c",
                        text="t",
                        target_node_id="b",
                        conditions=[BranchCondition("f", ConditionOperator.EQUALS, True)],
                    )
                ],
            )
        )
        d = g.to_dict()
        assert d["entry_node_id"] == "a"
        restored = IFRouteGraph.from_dict(d)
        assert "a" in restored.nodes
        assert restored.nodes["a"].choices[0].conditions[0].variable == "f"

    def test_from_dict_empty(self):
        g = IFRouteGraph.from_dict({})
        assert g.nodes == {}
        assert g.metadata == {}
        assert g.entry_node_id == ""


class TestIFRouteGenerator:
    def test_generate_from_series(self):
        gen = IFRouteGenerator("fantasy", {})
        graph = gen.generate_from_series(make_series(3))
        assert graph.entry_node_id == "prologue"
        assert "ep1_main" in graph.nodes
        assert "ep1_side" in graph.nodes

    def test_prologue_loop_genre(self):
        gen = IFRouteGenerator("loop", {})
        node = gen._create_prologue_node(make_series(1))
        assert any(c.id == "prologue_true_route" for c in node.choices)

    def test_prologue_aku_reijo_genre(self):
        gen = IFRouteGenerator("aku_reijo", {})
        node = gen._create_prologue_node(make_series(1))
        assert any(c.id == "prologue_flag_avoid" for c in node.choices)

    def test_prologue_content_from_metadata(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_prologue_node(make_series(1, metadata={"prologue": "はいはい"}))
        assert node.content == "はいはい"

    def test_catharsis_choices_zarma(self):
        gen = IFRouteGenerator("zarma", {})
        choices = gen._create_catharsis_choices(1, make_series(1))
        assert any("complete" in c.id for c in choices)

    def test_catharsis_choices_aku_reijo(self):
        gen = IFRouteGenerator("aku_reijo", {})
        choices = gen._create_catharsis_choices(1, make_series(1))
        assert any("happy_end" in c.id for c in choices)

    def test_catharsis_choices_generic(self):
        gen = IFRouteGenerator("fantasy", {})
        choices = gen._create_catharsis_choices(1, make_series(1))
        assert len(choices) == 2

    def test_normal_choices_genre_variants(self):
        for genre, needle in (
            ("loop", "loop_optimize"),
            ("cheat_tensei", "skill_experiment"),
            ("ts_tensei", "yuri_deepen"),
        ):
            gen = IFRouteGenerator(genre, {})
            choices = gen._create_normal_choices(1, make_series(1))
            assert any(needle in c.id for c in choices), genre

    def test_normal_choices_ep8_target(self):
        gen = IFRouteGenerator("fantasy", {})
        choices = gen._create_normal_choices(8, make_series(9))
        first = choices[0]
        assert first.target_node_id == "ending_main"

    def test_normal_choices_ep1_target(self):
        gen = IFRouteGenerator("fantasy", {})
        choices = gen._create_normal_choices(1, make_series(9))
        assert choices[0].target_node_id == "ep2_main"

    def test_should_create_subroute(self):
        gen = IFRouteGenerator("fantasy", {})
        assert gen._should_create_subroute(3, make_series(3)) is True
        assert gen._should_create_subroute(1, make_series(3)) is False
        loop_gen = IFRouteGenerator("loop", {})
        assert loop_gen._should_create_subroute(1, make_series(3)) is True
        aku_gen = IFRouteGenerator("aku_reijo", {})
        assert aku_gen._should_create_subroute(2, make_series(3)) is True

    def test_create_subroute_nodes(self):
        gen = IFRouteGenerator("fantasy", {})
        nodes = gen._create_subroute_nodes(3, "ep3_main", make_series(5))
        assert [n.id for n in nodes] == ["ep3_hidden"]

    def test_create_subroute_nodes_with_bad(self):
        gen = IFRouteGenerator("fantasy", {})
        nodes = gen._create_subroute_nodes(4, "ep4_main", make_series(6))
        assert [n.id for n in nodes] == ["ep4_hidden", "ep4_bad"]

    def test_create_merge_node(self):
        gen = IFRouteGenerator("fantasy", {})
        main = RouteNode(id="ep1_main", episode_num=1, content="", branch_type=BranchType.CHOICE)
        node = gen._create_merge_node(1, [main])
        assert node.branch_type == BranchType.MERGE
        assert node.parent_ids == ["ep1_main"]
        assert len(node.choices) == 2

    def test_create_episode_nodes_merge(self):
        gen = IFRouteGenerator("fantasy", {})
        nodes = gen._create_episode_nodes(make_episode(1), 1, "prologue", make_series(1))
        assert any(n.id == "ep1_merge" for n in nodes)

    def test_add_missing_target_nodes(self):
        gen = IFRouteGenerator("fantasy", {})
        graph = gen.generate_from_series(make_series(2))
        # 全てのターゲットが存在すること
        for node in graph.nodes.values():
            for c in node.choices:
                if c.target_node_id:
                    assert c.target_node_id in graph.nodes

    def test_create_ending_node(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_ending_node("ending_bad_1", make_series(1))
        assert node.metadata["ending_type"] == "bad_1"
        assert "バッドエンド1" in node.content

    def test_create_ending_node_unknown(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_ending_node("ending_zzz", make_series(1))
        assert "エンディング: zzz" in node.content

    def test_create_catharsis_variant_node(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_catharsis_variant_node("ep1_catharsis_complete", make_series(1))
        assert "完全カタルシス" in node.content
        assert node.choices[0].target_node_id == "ending_main"

    def test_create_catharsis_variant_node_unknown(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_catharsis_variant_node("ep1_catharsis_zzz", make_series(1))
        assert "カタルシス: zzz" in node.content

    def test_create_ending_variant_nodes(self):
        gen = IFRouteGenerator("fantasy", {})
        series = make_series(1)
        for nid, variant in (
            ("ep1_happy_end", "happy"),
            ("ep1_bittersweet", "bittersweet"),
            ("ep1_open_end", "open"),
            ("ep1_true_route", "true"),
            ("ep1_flag_avoid", "flag_avoid"),
        ):
            node = gen._create_ending_variant_node(nid, series)
            assert node.metadata["variant"] == variant, nid

    def test_create_ending_variant_node_fallback(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_ending_variant_node("ep1_xx_end", make_series(1))
        assert node.metadata["variant"] == "special"

    def test_create_side_event_node(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_side_event_node("ep2_side")
        assert node.episode_num == 2
        assert node.choices[0].target_node_id == "ep2_main"

    def test_create_side_event_node_non_digit(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_side_event_node("xx_side")
        assert node.episode_num == 0
        assert node.choices[0].target_node_id == "ending_main"

    def test_create_side_node(self):
        gen = IFRouteGenerator("fantasy", {})
        assert gen._create_side_node("ep1_side").id == "ep1_side"

    def test_create_optimized_node(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_optimized_node("ep1_optimized")
        assert node.choices[0].target_node_id == "ep1_main"

    def test_create_skill_combo_node(self):
        gen = IFRouteGenerator("fantasy", {})
        assert gen._create_skill_combo_node("ep1_skill_combo").choices[0].target_node_id == "ep1_main"

    def test_create_yuri_scene_node(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_yuri_scene_node("ep1_yuri_scene")
        assert node.choices[0].target_node_id == "ep1_main"
        assert node.metadata["mood"] == "sweet"

    def test_create_prologue_variant_node(self):
        gen = IFRouteGenerator("fantasy", {})
        assert gen._create_prologue_variant_node("ep1_flashback").metadata["variant"] == "flashback"
        assert gen._create_prologue_variant_node("ep1_action").metadata["variant"] == "action"
        assert gen._create_prologue_variant_node("ep1_true_route").metadata["variant"] == "true_route"
        assert gen._create_prologue_variant_node("zzz").metadata["variant"] == "special"

    def test_create_bad_ending_node(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_bad_ending_node("ending_bad_4")
        assert node.episode_num == 4
        assert node.choices[0].target_node_id == "ep4_main"

    def test_create_bad_ending_node_non_digit(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_bad_ending_node("ending_bad_xx")
        assert node.episode_num == 99
        assert node.choices[0].target_node_id == "prologue"

    def test_create_final_ending_nodes(self):
        gen = IFRouteGenerator("fantasy", {})
        s = make_series(1)
        assert gen._create_final_ending_node("ending_true", s).metadata["variant"] == "true"
        assert gen._create_final_ending_node("ending_normal", s).metadata["variant"] == "normal"
        assert gen._create_final_ending_node("ending_main", s).metadata["variant"] == "main"

    def test_create_main_continuation_node(self):
        gen = IFRouteGenerator("fantasy", {})
        assert gen._create_main_continuation_node("ep3_main").episode_num == 4
        node = gen._create_main_continuation_node("ep8_main")
        assert node.choices[0].target_node_id == "ending_main"

    def test_create_main_continuation_node_non_digit(self):
        gen = IFRouteGenerator("fantasy", {})
        assert gen._create_main_continuation_node("zz_main").episode_num == 1

    def test_create_hidden_continuation_node(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_hidden_continuation_node("ep3_hidden")
        assert node.choices[0].target_node_id == "ep4_hidden"
        assert node.choices[1].target_node_id == "ep4_main"

    def test_create_hidden_continuation_node_end(self):
        gen = IFRouteGenerator("fantasy", {})
        node = gen._create_hidden_continuation_node("ep8_hidden")
        assert node.choices[0].target_node_id == "ending_true"
        assert node.choices[1].target_node_id == "ending_main"

    def test_create_hidden_continuation_node_non_digit(self):
        gen = IFRouteGenerator("fantasy", {})
        assert gen._create_hidden_continuation_node("zz_hidden").episode_num == 1

    def test_create_target_node_unknown(self):
        gen = IFRouteGenerator("fantasy", {})
        assert gen._create_target_node("totally_unknown", make_series(1)) is None

    def test_set_initial_context(self):
        gen = IFRouteGenerator("fantasy", {})
        gen.set_initial_context({"genre": "x", "flags": {"a": 1}, "variables": {"v": 2}})
        assert gen._flags == {"a": 1}
        assert gen._variables == {"v": 2}
        assert gen._context["genre"] == "x"

    def test_generate_loop_genre(self):
        gen = IFRouteGenerator("loop", {})
        graph = gen.generate_from_series(make_series(2))
        assert isinstance(graph.validate(), list)
        assert "ep1_true_route" in graph.nodes

    def test_generate_aku_reijo_genre(self):
        gen = IFRouteGenerator("aku_reijo", {})
        graph = gen.generate_from_series(make_series(5))
        assert "ep2_hidden" in graph.nodes

    def test_generate_cheat_tensei_genre(self):
        gen = IFRouteGenerator("cheat_tensei", {})
        graph = gen.generate_from_series(make_series(3))
        assert "ep1_skill_combo" in graph.nodes

    def test_generate_ts_tensei_genre(self):
        gen = IFRouteGenerator("ts_tensei", {})
        graph = gen.generate_from_series(make_series(3))
        assert "ep1_yuri_scene" in graph.nodes

    def test_generate_zarma_catharsis(self):
        gen = IFRouteGenerator("zarma", {})
        graph = gen.generate_from_series(make_series(2))
        assert "ep2_catharsis_complete" in graph.nodes


class TestIFRoutePlayer:
    def build_graph(self) -> IFRouteGraph:
        g = IFRouteGraph(entry_node_id="a", metadata={"genre": "fantasy"})
        g.add_node(
            RouteNode(
                id="a",
                episode_num=1,
                content="",
                branch_type=BranchType.CHOICE,
                choices=[
                    RouteChoice(id="c1", text="go", target_node_id="b", effects={"flags.f": True}),
                    RouteChoice(
                        id="c2",
                        text="locked",
                        target_node_id="c",
                        conditions=[BranchCondition("flags.f", ConditionOperator.EQUALS, True)],
                    ),
                ],
            )
        )
        g.add_node(RouteNode(id="b", episode_num=2, content="", branch_type=BranchType.MERGE, merge_target="c"))
        g.add_node(RouteNode(id="c", episode_num=3, content="", branch_type=BranchType.MERGE))
        return g

    def test_get_current_node(self):
        player = IFRoutePlayer(self.build_graph())
        assert player.get_current_node().id == "a"

    def test_get_available_choices(self):
        player = IFRoutePlayer(self.build_graph())
        assert len(player.get_available_choices()) == 1

    def test_get_available_choices_no_node(self):
        player = IFRoutePlayer(IFRouteGraph(entry_node_id="zzz"))
        assert player.get_available_choices() == []
        assert player.get_state()["current_node"] is None

    def test_make_choice(self):
        player = IFRoutePlayer(self.build_graph())
        assert player.make_choice("c1") is True
        assert player.current_node_id == "c"
        assert player.context["flags"]["f"] is True
        assert player.context["history"][0]["choice_id"] == "c1"
        assert len(player.save_points) == 1

    def test_make_choice_unknown(self):
        player = IFRoutePlayer(self.build_graph())
        assert player.make_choice("zzz") is False

    def test_make_choice_unavailable(self):
        player = IFRoutePlayer(self.build_graph())
        assert player.make_choice("c2") is False

    def test_make_choice_no_node(self):
        player = IFRoutePlayer(IFRouteGraph(entry_node_id="zzz"))
        assert player.make_choice("c1") is False

    def test_make_choice_no_target(self):
        g = IFRouteGraph(entry_node_id="a")
        g.add_node(
            RouteNode(
                id="a",
                episode_num=1,
                content="",
                branch_type=BranchType.CHOICE,
                choices=[RouteChoice(id="c1", text="stay", target_node_id="")],
            )
        )
        player = IFRoutePlayer(g)
        assert player.make_choice("c1") is True
        assert player.current_node_id == "a"

    def test_load_save(self):
        player = IFRoutePlayer(self.build_graph())
        player.make_choice("c1")
        assert player.load_save(0) is True
        assert player.current_node_id == "a"
        assert player.load_save(5) is False
        assert player.load_save(-1) is False

    def test_get_state(self):
        player = IFRoutePlayer(self.build_graph())
        state = player.get_state()
        assert state["current_node"]["id"] == "a"
        assert state["available_choices"][0]["available"] is True
        assert state["save_points_count"] == 0

    def test_export_playthrough(self):
        player = IFRoutePlayer(self.build_graph())
        player.make_choice("c1")
        out = player.export_playthrough()
        assert out["genre"] == "fantasy"
        assert out["final_ending"] == "unknown"
        assert out["flags"] == {"f": True}
        assert "timestamp" in out

    def test_export_playthrough_unknown_genre(self):
        player = IFRoutePlayer(IFRouteGraph(entry_node_id=""))
        assert player.export_playthrough()["genre"] == "unknown"

    def test_auto_progress_after_choice(self):
        g = IFRouteGraph(entry_node_id="a")
        g.add_node(
            RouteNode(
                id="a",
                episode_num=1,
                content="",
                branch_type=BranchType.CHOICE,
                choices=[RouteChoice(id="c1", text="go", target_node_id="m")],
            )
        )
        g.add_node(RouteNode(id="m", episode_num=2, content="", branch_type=BranchType.MERGE, merge_target="z"))
        player = IFRoutePlayer(g)
        player.make_choice("c1")
        assert player.current_node_id == "z"

    def test_create_if_route_system(self):
        graph = create_if_route_system("fantasy", make_series(2), {})
        assert isinstance(graph, IFRouteGraph)
        assert graph.entry_node_id == "prologue"
