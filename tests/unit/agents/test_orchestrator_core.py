"""src/agents/orchestrator.py の単体テスト."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.orchestrator import (
    AgentContext,
    AgentName,
    AgentResult,
    CyclicDependencyError,
    Orchestrator,
    _make_skill_node,
)


def _result(next_agent=None, artifacts=None, **kw):
    return AgentResult(next_agent=next_agent, artifacts=artifacts or {}, **kw)


# ------------------------------------------------------------- dataclasses


def test_cyclic_dependency_error_is_value_and_runtime_error():
    assert issubclass(CyclicDependencyError, ValueError)
    assert issubclass(CyclicDependencyError, RuntimeError)


def test_agent_context_defaults():
    ctx = AgentContext(book_id=1, branch_id=1, ep_num=1)
    assert ctx.artifacts == {}
    assert ctx.backtrack_history == []


def test_agent_result_defaults():
    res = AgentResult(next_agent=None, artifacts={})
    assert res.should_retry is False
    assert res.error is None
    assert res.is_backtrack is False


class _FakeSkill:
    def __init__(self, result):
        self._result = result

    async def run(self, ctx):
        return self._result


async def test_make_skill_node_sets_next():
    inst = _FakeSkill(_result())
    node = _make_skill_node(inst, "plot")
    res = await node(AgentContext(1, 1, 1))
    assert res.next_agent == "plot"


async def test_make_skill_node_keeps_explicit_next():
    inst = _FakeSkill(_result(next_agent="writing"))
    node = _make_skill_node(inst, "plot")
    res = await node(AgentContext(1, 1, 1))
    assert res.next_agent == "writing"


async def test_make_skill_node_does_not_override_on_error():
    inst = _FakeSkill(_result(error="boom"))
    node = _make_skill_node(inst, "plot")
    res = await node(AgentContext(1, 1, 1))
    assert res.next_agent is None


# ------------------------------------------------------------ construction


def test_init_defaults():
    orch = Orchestrator(nodes={})
    assert orch.correlation_id == "unknown"
    assert orch.max_backtracks_per_node == 3
    assert orch.use_dag_scheduler is False
    assert orch.get_active_version() == "v1"
    assert orch.get_skill_class("nope") is None


# ---------------------------------------------------------- skill registry


class FakeSkillA:
    pass


def test_register_and_replace_skills(monkeypatch):
    orch = Orchestrator(nodes={})
    monkeypatch.setattr(
        "src.agents.skill_base.SkillAgent.discover_skills", staticmethod(lambda pkg: [FakeSkillA])
    )
    orch.register_discovered_skills()
    assert orch.get_skill_class("fakea") is FakeSkillA
    orch.replace_skill("fakea", int)
    assert orch.get_skill_class("fakea") is int
    with pytest.raises(KeyError):
        orch.replace_skill("missing", int)


def test_set_skill_version(monkeypatch):
    orch = Orchestrator(nodes={})
    monkeypatch.setattr(
        "src.agents.skill_base.SkillAgent.discover_skills", staticmethod(lambda pkg: [])
    )
    orch.set_skill_version("v2")
    assert orch.get_active_version() == "v2"
    with pytest.raises(ValueError, match="Unsupported skill version"):
        orch.set_skill_version("v9")


def test_set_skill_version_metrics_failure_is_swallowed(monkeypatch):
    orch = Orchestrator(nodes={})
    monkeypatch.setattr(
        "src.agents.skill_base.SkillAgent.discover_skills", staticmethod(lambda pkg: [FakeSkillA])
    )
    orch.set_skill_version("v1")
    assert orch.get_active_version() == "v1"


def test_get_skill_metrics():
    orch = Orchestrator(nodes={})
    assert isinstance(orch.get_skill_metrics(), dict)


# -------------------------------------------------------- build_execution_order


def test_build_execution_order_topological():
    orch = Orchestrator(nodes={})
    manifest = [
        {"name": "b", "depends_on": ["a"]},
        {"name": "a"},
        {"name": "c", "runs_after": ["b"]},
    ]
    assert orch.build_execution_order(manifest) == ["a", "b", "c"]


def test_build_execution_order_runs_before():
    orch = Orchestrator(nodes={})
    manifest = [{"name": "a", "runs_before": ["b"]}, {"name": "b"}]
    assert orch.build_execution_order(manifest) == ["a", "b"]


def test_build_execution_order_ignores_unknown_refs():
    orch = Orchestrator(nodes={})
    manifest = [{"name": "a", "depends_on": ["ghost"]}]
    assert orch.build_execution_order(manifest) == ["a"]


def test_build_execution_order_with_available_skills():
    orch = Orchestrator(nodes={})
    manifest = [{"name": "a"}, {"name": "b"}]
    order = orch.build_execution_order(manifest, {"a": FakeSkillA})
    assert order == [FakeSkillA]


def test_build_execution_order_with_pydantic_like_items():
    class Item:
        def __init__(self, data):
            self._d = data

        def model_dump(self, by_alias=True):
            return self._d

    orch = Orchestrator(nodes={})
    order = orch.build_execution_order([Item({"name": "x"}), Item({"name": "y"})])
    assert set(order) == {"x", "y"}


def test_build_execution_order_object_with_skills_attr():
    class Manifest:
        skills = [{"name": "a"}]

    orch = Orchestrator(nodes={})
    assert orch.build_execution_order(Manifest()) == ["a"]


def test_build_execution_order_cyclic_raises():
    orch = Orchestrator(nodes={})
    manifest = [{"name": "a", "depends_on": ["b"]}, {"name": "b", "depends_on": ["a"]}]
    with pytest.raises(CyclicDependencyError):
        orch.build_execution_order(manifest)


# ------------------------------------------------------------------ run loop


def _nodes(*specs):
    nodes = {}
    for name, result in specs:
        async def node(ctx, _r=result):
            if isinstance(_r, Exception):
                raise _r
            return _r
        nodes[name] = node
    return nodes


async def test_run_linear_pipeline():
    orch = Orchestrator(
        nodes=_nodes(
            ("planning", _result(next_agent="plot", artifacts={"p": 1})),
            ("plot", _result(next_agent=None, artifacts={"q": 2})),
        )
    )
    ctx = await orch.run(AgentContext(1, 1, 1))
    assert ctx.artifacts == {"p": 1, "q": 2}


async def test_run_with_explicit_start_and_enum():
    orch = Orchestrator(
        nodes=_nodes((AgentName.PLOT, _result(next_agent=None, artifacts={"x": 1})))
    )
    ctx = await orch.run(AgentContext(1, 1, 1), start=AgentName.PLOT)
    assert ctx.artifacts == {"x": 1}


async def test_run_uses_ordered_skill_names_first():
    orch = Orchestrator(
        nodes=_nodes(("b", _result(next_agent=None)), ("a", _result(next_agent=None)))
    )
    orch._ordered_skill_names = ["a"]
    ctx = await orch.run(AgentContext(1, 1, 1))
    assert ctx.artifacts == {}


async def test_run_without_nodes_raises():
    orch = Orchestrator(nodes={})
    with pytest.raises(ValueError, match="No registered nodes"):
        await orch.run(AgentContext(1, 1, 1))


async def test_run_unregistered_node_raises():
    orch = Orchestrator(nodes={})
    orch._ordered_skill_names = ["missing"]
    with pytest.raises(RuntimeError, match="Agent node not registered"):
        await orch.run(AgentContext(1, 1, 1))


async def test_run_error_continues_to_next():
    orch = Orchestrator(
        nodes=_nodes(
            ("a", _result(next_agent="b", error="oops")),
            ("b", _result(next_agent=None, artifacts={"done": True})),
        )
    )
    ctx = await orch.run(AgentContext(1, 1, 1))
    assert ctx.artifacts["a_error"] == "oops"
    assert ctx.artifacts["done"] is True


async def test_run_unexpected_exception_reraised():
    orch = Orchestrator(nodes=_nodes(("a", RuntimeError("boom"))))
    with pytest.raises(RuntimeError, match="Unexpected error in a"):
        await orch.run(AgentContext(1, 1, 1))


async def test_run_backtrack_within_limit():
    ctx = AgentContext(1, 1, 1)
    calls = {"a": 0}

    async def node_a(ctx):
        calls["a"] += 1
        if calls["a"] == 1:
            return _result(next_agent="a", should_retry=True, artifacts={"audit_score": 0.1})
        return _result(next_agent="b", artifacts={"ok": True})

    async def node_b(ctx):
        return _result(next_agent=None)

    orch = Orchestrator(nodes={"a": node_a, "b": node_b})
    out = await orch.run(ctx)
    assert out.artifacts["audit_status"] == "rejected"
    assert out.artifacts["audit_retry_count"] == 1
    assert out.artifacts["audit_score"] == 0.1
    assert out.backtrack_history[0] == {
        "from_node": "a",
        "to_node": "a",
        "reason": "audit_failed",
        "count": 1,
    }
    assert out.artifacts["backtrack_history"] is out.backtrack_history


async def test_run_backtrack_exceeds_max_proceeds_forward():
    orch = Orchestrator(nodes={}, max_backtracks_per_node=0)
    orch._ordered_skill_names = ["a"]

    async def node_a(ctx):
        return _result(next_agent="a", should_retry=True)

    async def node_b(ctx):
        return _result(next_agent=None, artifacts={"ok": True})

    orch.nodes = {"a": node_a, "b": node_b}
    out = await orch.run(AgentContext(1, 1, 1))
    assert out.artifacts["a_max_backtrack_exceeded"] is True
    assert out.artifacts["ok"] is True


async def test_run_backtrack_exceeds_max_at_last_node():
    orch = Orchestrator(nodes={}, max_backtracks_per_node=0)
    orch._ordered_skill_names = ["a"]

    async def node_a(ctx):
        return _result(next_agent="a", should_retry=True)

    orch.nodes = {"a": node_a}
    out = await orch.run(AgentContext(1, 1, 1))
    assert out.artifacts["a_max_backtrack_exceeded"] is True


async def test_run_with_event_bus_publishes_events():
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    orch = Orchestrator(
        nodes=_nodes(
            ("a", _result(next_agent="b", error="e")),
            ("b", _result(next_agent=None)),
        ),
        event_bus=bus,
    )
    await orch.run(AgentContext(1, 1, 3))
    statuses = [c.args[0].payload["status"] for c in bus.publish_async.call_args_list]
    assert "started" in statuses
    assert "failed" in statuses
    assert "error_continued" in statuses


async def test_run_backtrack_publishes_event():
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    orch = Orchestrator(nodes={}, event_bus=bus)
    orch._ordered_skill_names = ["a"]

    async def node_a(ctx):
        if ctx.artifacts.get("retried"):
            return _result(next_agent=None, artifacts={"ok": 1})
        return _result(next_agent="a", should_retry=True)

    orch.nodes = {"a": node_a}
    out = await orch.run(AgentContext(1, 1, 1))
    assert "audit_retry_count" in out.artifacts
    statuses = [c.args[0].payload["status"] for c in bus.publish_async.call_args_list]
    assert "backtracked" in statuses


# --------------------------------------------------------------- DAG branch


class _FakeNode:
    def __init__(self, status="completed", result=None):
        self.status = status
        self.result = result


class _FakeGraph:
    def __init__(self, nodes):
        self.nodes = nodes


async def test_run_with_dag_scheduler():
    dag = MagicMock()
    dag.register_task = MagicMock()
    dag.run_dag = AsyncMock(
        return_value=_FakeGraph(
            {
                "c_a": _FakeNode("completed", {"a": 1}),
                "c_b": _FakeNode("completed", "not-a-dict"),
                "c_c": _FakeNode("failed", {"x": 1}),
            }
        )
    )
    orch = Orchestrator(nodes={}, dag_scheduler=dag, use_dag_scheduler=True, correlation_id="c")
    orch._ordered_skill_names = ["a", "b"]
    orch._skill_instances = {}
    ctx = await orch.run(AgentContext(1, 1, 1))
    assert ctx.artifacts["a"] == 1
    assert ctx.artifacts["c_b"] == "not-a-dict"
    assert "c_c" not in ctx.artifacts


async def test_dag_wrapper_success_and_failure():
    dag = MagicMock()
    dag.register_task = MagicMock()
    orch = Orchestrator(nodes={}, dag_scheduler=dag, use_dag_scheduler=True, correlation_id="c")
    orch._ordered_skill_names = ["a"]
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    orch.event_bus = bus
    inst = MagicMock()
    inst.run = AsyncMock(return_value=_result(next_agent=None, artifacts={"v": 1}))
    orch._skill_instances = {"a": inst}
    dag.run_dag = AsyncMock(return_value=_FakeGraph({}))
    await orch.run(AgentContext(1, 1, 5))
    wrapper = dag.register_task.call_args[0][1]
    out = await wrapper(task_id="c_a")
    assert out == {"v": 1}

    inst.run = AsyncMock(return_value=_result(next_agent=None, error="bad"))
    with pytest.raises(RuntimeError, match="failed: bad"):
        await wrapper(task_id="c_a2")

    inst.run = AsyncMock(side_effect=ValueError("unexpected"))
    with pytest.raises(ValueError):
        await wrapper(task_id="c_a3")

    # 前のタスク結果を引き継ぐ
    inst.run = AsyncMock(return_value=_result(next_agent=None, artifacts={"w": 2}))
    await wrapper(task_id="c_a4", input_from="c_a")
    assert inst.run.call_args[0][0].artifacts == {"v": 1}


def test_register_skills_to_scheduler_noop_without_scheduler():
    orch = Orchestrator(nodes={})
    orch._register_skills_to_scheduler()
    assert True


def test_build_dag_graph():
    orch = Orchestrator(nodes={}, correlation_id="cid")
    orch._ordered_skill_names = ["s1", "s2"]
    graph = orch._build_dag_graph()
    assert "cid_s1" in graph.nodes
    assert "cid_s2" in graph.nodes
    assert graph.nodes["cid_s2"].dependencies == ["cid_s1"]


# ------------------------------------------------------------------- A/B test


class AbSkillV:
    ok = True

    def __init__(self):
        self._last_duration = 0.1

    async def execute(self, ctx):
        if self.ok:
            return _result(next_agent=None)
        raise RuntimeError("fail")


def _patch_skills(monkeypatch, cls=AbSkillV):
    # スキル名はクラス名から導出されるため、クラス名 'AbSkillV' -> 'AbSkillV'
    monkeypatch.setattr(
        "src.agents.skill_base.SkillAgent.discover_skills", staticmethod(lambda pkg: [cls])
    )


async def test_run_ab_test_rejects_bad_version():
    orch = Orchestrator(nodes={})
    with pytest.raises(ValueError, match="Versions must be"):
        await orch.run_ab_test("abv", "v1", "v3", [])


async def test_run_ab_test_success(monkeypatch):
    _patch_skills(monkeypatch)
    orch = Orchestrator(nodes={})
    ctxs = [AgentContext(1, 1, 1, artifacts={"k": 1})]
    res = await orch.run_ab_test("abv", "v1", "v2", ctxs)
    assert res["version_a"]["samples"] == 1
    assert res["winner"] in ("a", "b", "tie")
    assert 0.0 <= res["p_value"] <= 1.0
    assert res["metric_key"] == "avg_duration_sec"


async def test_run_ab_test_skill_missing(monkeypatch):
    _patch_skills(monkeypatch, cls=type("Other", (), {}))
    orch = Orchestrator(nodes={})
    with pytest.raises(ValueError, match="not found in version"):
        await orch.run_ab_test("abv", "v1", "v2", [AgentContext(1, 1, 1)])


async def test_run_ab_test_all_failures(monkeypatch):
    class Failing(AbSkillV):
        ok = False

    _patch_skills(monkeypatch, cls=Failing)
    orch = Orchestrator(nodes={})
    res = await orch.run_ab_test("failing", "v1", "v2", [AgentContext(1, 1, 1)])
    assert res["winner"] == "tie"
    assert res["p_value"] == 1.0


async def test_run_ab_test_winner_a(monkeypatch):
    # 両バージョンが同名のスキルクラス registered を持つ必要がある
    fast = type("CmpSkill", (AbSkillV,), {"__init__": lambda self: setattr(self, "_last_duration", 0.0) or None})
    slow = type("CmpSkill", (AbSkillV,), {"__init__": lambda self: setattr(self, "_last_duration", 5.0) or None})

    def discover(pkg):
        return [fast if pkg.endswith("v1") else slow]

    monkeypatch.setattr(
        "src.agents.skill_base.SkillAgent.discover_skills", staticmethod(discover)
    )
    orch = Orchestrator(nodes={})
    res = await orch.run_ab_test("cmp", "v1", "v2", [AgentContext(1, 1, 1)])
    assert res["winner"] == "a"
    assert res["version_a"]["metrics"]["avg_duration"] == 0.0
    assert res["version_b"]["metrics"]["avg_duration"] == 5.0


async def test_run_ab_test_winner_b(monkeypatch):
    slow = type("CmpSkill2", (AbSkillV,), {"__init__": lambda self: setattr(self, "_last_duration", 5.0) or None})
    fast = type("CmpSkill2", (AbSkillV,), {"__init__": lambda self: setattr(self, "_last_duration", 0.0) or None})

    def discover(pkg):
        return [slow if pkg.endswith("v1") else fast]

    monkeypatch.setattr(
        "src.agents.skill_base.SkillAgent.discover_skills", staticmethod(discover)
    )
    orch = Orchestrator(nodes={})
    res = await orch.run_ab_test("cmp2", "v1", "v2", [AgentContext(1, 1, 1)])
    assert res["winner"] == "b"


async def test_run_ab_test_success_rate_winner_b(monkeypatch):
    class Base(AbSkillV):
        pass

    bad = type("WinSkill", (Base,), {"ok": False})
    good = type("WinSkill", (Base,), {"ok": True})

    def discover(pkg):
        return [bad if pkg.endswith("v1") else good]

    monkeypatch.setattr(
        "src.agents.skill_base.SkillAgent.discover_skills", staticmethod(discover)
    )
    orch = Orchestrator(nodes={})
    res = await orch.run_ab_test("win", "v1", "v2", [AgentContext(1, 1, 1)])
    assert res["winner"] == "b"
    assert res["version_a"]["metrics"]["success_rate"] == 0.0
    assert res["version_b"]["metrics"]["success_rate"] == 1.0
    assert 0.0 < res["p_value"] < 1.0


async def test_run_ab_test_version_b_skill_missing(monkeypatch):
    class OnlyV1(AbSkillV):
        pass

    class OnlyV1b(AbSkillV):
        pass

    calls = {"n": 0}

    def discover(pkg):
        calls["n"] += 1
        return [OnlyV1 if calls["n"] == 1 else OnlyV1b]

    monkeypatch.setattr(
        "src.agents.skill_base.SkillAgent.discover_skills", staticmethod(discover)
    )
    orch = Orchestrator(nodes={})
    with pytest.raises(ValueError, match="not found in version v2"):
        await orch.run_ab_test("onlyv1", "v1", "v2", [AgentContext(1, 1, 1)])


async def test_run_exception_publishes_exception_continued():
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    orch = Orchestrator(nodes=_nodes(("a", RuntimeError("boom"))), event_bus=bus)
    with pytest.raises(RuntimeError):
        await orch.run(AgentContext(1, 1, 1))
    statuses = [c.args[0].payload["status"] for c in bus.publish_async.call_args_list]
    assert "exception_continued" in statuses


async def test_run_ab_test_empty_contexts(monkeypatch):
    _patch_skills(monkeypatch)
    orch = Orchestrator(nodes={})
    res = await orch.run_ab_test("abv", "v1", "v2", [])
    assert res["version_a"]["samples"] == 0
    assert res["p_value"] == 1.0


async def test_schedule_ab_test_in_loop(monkeypatch):
    _patch_skills(monkeypatch)
    orch = Orchestrator(nodes={})
    task = orch.schedule_ab_test("abv", "v1", "v2", 1.0, min_samples=2)
    assert isinstance(task, asyncio.Task)
    result = await task
    assert result["metric_key"] == "avg_duration_sec"
    assert orch._ab_test_tasks == set()


def test_schedule_ab_test_sync_context(monkeypatch):
    _patch_skills(monkeypatch)
    orch = Orchestrator(nodes={})
    result = orch.schedule_ab_test("abv", "v1", "v2", 1.0, min_samples=1)
    assert result["winner"] in ("a", "b", "tie")


def test_log_ab_test_result_cancelled():
    task = MagicMock()
    task.cancelled.return_value = True
    Orchestrator._log_ab_test_result(task)
    task.exception.assert_not_called()


def test_log_ab_test_result_with_exception():
    task = MagicMock()
    task.cancelled.return_value = False
    task.exception.return_value = ValueError("x")
    Orchestrator._log_ab_test_result(task)


def test_log_ab_test_result_ok():
    task = MagicMock()
    task.cancelled.return_value = False
    task.exception.return_value = None
    Orchestrator._log_ab_test_result(task)


def test_promote_ab_winner(monkeypatch):
    _patch_skills(monkeypatch)
    orch = Orchestrator(nodes={})
    orch.promote_ab_winner("abv", "v2")
    assert orch.get_active_version() == "v2"
    with pytest.raises(ValueError, match="Invalid version"):
        orch.promote_ab_winner("abv", "v3")
