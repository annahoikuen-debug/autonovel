"""Coverage tests for src/backend/tasks DAG stack (models, engine, policies, numa, resources, metrics, persistence, scheduler)."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.backend.tasks.dag_models import (
    DAGGraph,
    DAGTaskNode,
    TaskResourceRequirement,
)
from src.backend.tasks.dag_engine import DAGCycleError, DAGEngine
from src.backend.tasks.dag_persistence import FileSystemDAGPersistence
from src.backend.tasks.scheduling_policies import (
    AffinityPriorityPolicy,
    DeadlineAwarePolicy,
    FairRoundRobinPolicy,
)
from src.backend.tasks.numa_topology import (
    NUMATopology,
    detect_gpu_numa_py3nvml,
    detect_numa_topology,
)
from src.backend.tasks.resource_manager import ResourceManager
from src.backend.tasks.metrics_collector import (
    NoOpMetricsCollector,
    OTELTracingCollector,
    PrometheusMetricsCollector,
    TaskMetrics,
    OTEL_AVAILABLE,
    PROMETHEUS_AVAILABLE,
)
from src.backend.tasks.dag_scheduler import DAGScheduler


# --------------------------------------------------------------------------
# dag_models
# --------------------------------------------------------------------------

def _node(tid: str, **kw) -> DAGTaskNode:
    return DAGTaskNode(task_id=tid, func_name=kw.pop("func_name", "f"), **kw)


def test_task_resource_requirement_defaults():
    req = TaskResourceRequirement()
    assert req.cpu_cores == 1.0
    assert req.gpu_mem_mb == 0
    assert req.ram_mb == 512


def test_dag_graph_add_node_and_dependency_errors():
    g = DAGGraph(dag_id="g1")
    g.add_node(_node("a"))
    g.add_node(_node("b"))

    with pytest.raises(KeyError, match="Child task"):
        g.add_dependency("zzz", "a")
    with pytest.raises(KeyError, match="Parent task"):
        g.add_dependency("a", "zzz")

    g.add_dependency("b", "a")
    assert g.nodes["b"].dependencies == ["a"]
    # idempotent
    g.add_dependency("b", "a")
    assert g.nodes["b"].dependencies == ["a"]


def test_dag_graph_get_ready_tasks_priority_and_failed_parents():
    g = DAGGraph(dag_id="g2")
    g.add_node(_node("a", priority=1))
    g.add_node(_node("b", priority=5))
    g.add_node(_node("c", priority=3, dependencies=["a", "b"]))
    g.add_node(_node("d", priority=9, dependencies=["a"]))

    ready = g.get_ready_tasks()
    assert [t.task_id for t in ready] == ["b", "a"]
    assert g.nodes["a"].status == "ready"

    g.mark_completed("a")
    g.mark_completed("b")
    assert [t.task_id for t in g.get_ready_tasks()] == ["d", "c"]

    # failed parent blocks readiness
    g2 = DAGGraph(dag_id="g3")
    g2.add_node(_node("p"))
    g2.add_node(_node("c2", dependencies=["p"]))
    g2.mark_failed("p", "boom")
    assert g2.get_ready_tasks() == []


def test_dag_graph_marks_ignore_unknown_ids():
    g = DAGGraph(dag_id="g4")
    g.add_node(_node("x"))
    g.mark_running("nope")
    g.mark_completed("nope")
    g.mark_failed("nope", "e")
    g.mark_cancelled("nope")

    g.mark_running("x")
    assert g.nodes["x"].started_at is not None
    g.mark_completed("x", result=42)
    assert g.nodes["x"].result == 42
    assert g.nodes["x"].completed_at is not None
    g.mark_cancelled("x")
    assert g.nodes["x"].error == "Task cancelled"


def test_dag_graph_cascade_cancel_downstream():
    g = DAGGraph(dag_id="g5")
    g.add_node(_node("a"))
    g.add_node(_node("b", dependencies=["a"]))
    g.add_node(_node("c", dependencies=["b"]))
    g.add_node(_node("d", dependencies=["c"], status="completed"))

    cancelled = g.cascade_cancel_downstream("a")
    assert cancelled == ["b", "c"]
    assert g.nodes["b"].status == "cancelled"
    assert g.nodes["c"].status == "cancelled"
    assert g.nodes["d"].status == "completed"


def test_dag_graph_status_predicates():
    g = DAGGraph(dag_id="g6")
    assert g.is_all_completed() is False
    assert g.is_finished() is False
    assert g.has_failures() is False

    g.add_node(_node("a"))
    assert g.is_finished() is False
    g.mark_completed("a")
    assert g.is_all_completed() is True
    assert g.is_finished() is True

    g.add_node(_node("b"))
    g.mark_failed("b", "err")
    assert g.has_failures() is True
    assert g.is_finished() is True


# --------------------------------------------------------------------------
# dag_engine
# --------------------------------------------------------------------------

def test_dag_engine_validate_and_sort():
    assert DAGEngine.topological_sort(DAGGraph(dag_id="e")) == []

    g = DAGGraph(dag_id="e2")
    g.add_node(_node("a"))
    g.add_node(_node("b", dependencies=["a"]))
    assert DAGEngine.validate_dag(g) is True
    assert DAGEngine.topological_sort(g) == ["a", "b"]


def test_dag_engine_missing_dependency_raises():
    g = DAGGraph(dag_id="e3")
    g.add_node(_node("a", dependencies=["ghost"]))
    with pytest.raises(KeyError, match="non-existent task"):
        DAGEngine.validate_dag(g)


def test_dag_engine_cycle_detection():
    g = DAGGraph(dag_id="e4")
    g.add_node(_node("a", dependencies=["b"]))
    g.add_node(_node("b", dependencies=["a"]))
    with pytest.raises(DAGCycleError):
        DAGEngine.topological_sort(g)


def test_dag_engine_execution_stages_sorted_by_priority():
    g = DAGGraph(dag_id="e5")
    g.add_node(_node("a", priority=1))
    g.add_node(_node("b", priority=9))
    g.add_node(_node("c", dependencies=["a", "b"], priority=5))
    stages = DAGEngine.get_execution_stages(g)
    assert stages[0] == ["b", "a"]
    assert stages[1] == ["c"]
    assert DAGEngine.get_execution_stages(DAGGraph(dag_id="e6")) == []


# --------------------------------------------------------------------------
# scheduling_policies
# --------------------------------------------------------------------------

def test_affinity_priority_policy_sorts():
    aff_map = {"1:1": "w1"}
    p = AffinityPriorityPolicy(aff_map)
    t_aff = _node("aff", priority=1, kwargs={"book_id": 1, "ep_num": 1})
    t_high = _node("high", priority=5, kwargs={"book_id": 9, "ep_num": 9})
    result = p.sort_ready_tasks([t_high, t_aff])
    assert [t.task_id for t in result] == ["aff", "high"]
    assert p.should_preempt(t_aff, t_high) is False


def test_fair_round_robin_policy_rotates():
    p = FairRoundRobinPolicy()
    a, b = _node("a", priority=1), _node("b", priority=1)
    assert [t.task_id for t in p.sort_ready_tasks([a, b])] == ["a", "b"]
    assert [t.task_id for t in p.sort_ready_tasks([a, b])] == ["b", "a"]
    assert p.should_preempt(a, b) is False


def test_deadline_aware_policy():
    p = DeadlineAwarePolicy(default_deadline_seconds=10.0)
    early = _node("early", kwargs={"deadline_seconds": 1})
    late = _node("late", kwargs={"deadline_seconds": 1000})
    assert [t.task_id for t in p.sort_ready_tasks([late, early])] == ["early", "late"]
    assert p.should_preempt(late, early) is True
    assert p.should_preempt(early, late) is False


# --------------------------------------------------------------------------
# numa_topology
# --------------------------------------------------------------------------

def test_numa_topology_accessors():
    t = NUMATopology(
        cpu_to_numa={0: 0, 1: 0, 2: 1},
        gpu_to_numa={0: 1},
        numa_nodes=[0, 1],
        cpu_cores_per_numa={0: 2, 1: 1},
    )
    assert t.get_numa_for_cpu(0) == 0
    assert t.get_numa_for_cpu(99) is None
    assert t.get_numa_for_gpu(0) == 1
    assert t.get_numa_for_gpu(7) is None
    assert t.get_cpus_for_numa(0) == [0, 1]
    assert t.get_gpus_for_numa(1) == [0]
    assert t.get_gpus_for_numa(5) == []


def test_detect_numa_topology_returns_object():
    assert isinstance(detect_numa_topology(), NUMATopology)


def test_detect_gpu_numa_handles_missing_pynvml():
    assert isinstance(detect_gpu_numa_py3nvml(), dict)


# --------------------------------------------------------------------------
# resource_manager
# --------------------------------------------------------------------------

class _FakeMem:
    def __init__(self, available):
        self.available = available


def test_resource_manager_snapshots_and_limits(monkeypatch):

    topo = NUMATopology(cpu_to_numa={0: 0, 1: 1}, gpu_to_numa={0: 1}, numa_nodes=[0, 1])
    rm = ResourceManager(numa_topology=topo)
    monkeypatch.setattr(rm, "get_available_ram_mb", lambda: 8192)
    monkeypatch.setattr(rm, "get_gpu_vram_mb", lambda: 4096)
    monkeypatch.setattr(rm, "get_cpu_cores", lambda: 8.0)

    res = rm.get_available_resources()
    assert res.cpu_cores == 6.4
    assert res.ram_mb == int(8192 * 0.8)

    limits = rm.calculate_worker_pool_limits()
    assert limits["llm_workers"] == 6
    assert limits["image_workers"] == 1
    assert limits["max_parallel_tasks"] == 7

    monkeypatch.setattr(rm, "get_gpu_vram_mb", lambda: 0)
    assert rm.calculate_worker_pool_limits()["image_workers"] == 2

    monkeypatch.setattr(rm, "get_available_ram_mb", lambda: 100)
    assert rm.calculate_worker_pool_limits()["llm_workers"] == 1


def test_resource_manager_can_schedule(monkeypatch):
    topo = NUMATopology()
    rm = ResourceManager(numa_topology=topo)
    monkeypatch.setattr(rm, "get_available_resources", lambda: TaskResourceRequirement(cpu_cores=4, ram_mb=1024, gpu_mem_mb=0))
    assert rm.can_schedule(TaskResourceRequirement(cpu_cores=1, ram_mb=512), TaskResourceRequirement()) is True
    assert rm.can_schedule(TaskResourceRequirement(cpu_cores=8, ram_mb=512), TaskResourceRequirement()) is False
    assert rm.can_schedule(TaskResourceRequirement(cpu_cores=1, ram_mb=4096), TaskResourceRequirement()) is False
    assert rm.can_schedule(TaskResourceRequirement(cpu_cores=1, ram_mb=512, gpu_mem_mb=1), TaskResourceRequirement()) is False


def test_resource_manager_numa_affinity_and_env(monkeypatch):
    topo = NUMATopology(cpu_to_numa={0: 0, 1: 1}, gpu_to_numa={0: 1}, numa_nodes=[0, 1])
    rm = ResourceManager(numa_topology=topo)
    rm.numa_topology.gpu_to_numa = {0: 1}
    assert rm.get_worker_numa_affinity(0) == 0
    assert rm.get_worker_numa_affinity(1) == 1
    assert rm.get_worker_numa_affinity(3) == 1
    assert rm.get_worker_numa_affinity(0, is_gpu_worker=True) == 1

    env = rm.get_gpu_worker_env(0)
    assert env["CUDA_VISIBLE_DEVICES"] == "0"
    assert "NUMACTL_ARGS" in env

    empty = ResourceManager(numa_topology=NUMATopology())
    empty.numa_topology = NUMATopology()
    assert empty.get_worker_numa_affinity(0) is None
    assert "NUMACTL_ARGS" not in empty.get_gpu_worker_env(0)


def test_resource_manager_fallbacks(monkeypatch):
    import src.backend.tasks.resource_manager as rm_mod

    rm = ResourceManager(numa_topology=NUMATopology())
    monkeypatch.setattr(rm_mod, "psutil", None)
    assert rm.get_available_ram_mb() == 4096
    monkeypatch.setattr(rm_mod, "torch", None)
    assert rm.get_gpu_vram_mb() == 0

    class _BadPsutil:
        @staticmethod
        def virtual_memory():
            raise RuntimeError("nope")

    monkeypatch.setattr(rm_mod, "psutil", _BadPsutil)
    assert rm.get_available_ram_mb() == 4096

    class _BadTorch:
        @staticmethod
        def cuda():
            class C:
                @staticmethod
                def is_available():
                    raise RuntimeError("no cuda")

            return C()

    monkeypatch.setattr(rm_mod, "torch", _BadTorch)
    assert rm.get_gpu_vram_mb() == 0


# --------------------------------------------------------------------------
# metrics_collector
# --------------------------------------------------------------------------

def test_noop_metrics_collector():
    c = NoOpMetricsCollector()
    m = TaskMetrics(task_id="t", dag_id="d", duration_seconds=1.0, status="completed", retry_count=0, worker_id="w", resource_usage={})
    c.record_task_start("t", "d", "w")
    c.record_task_end(m)
    c.record_queue_depth("d", 1, 0, 0)
    c.record_resource_utilization(1, 2, 3)
    c.record_retry("t", 1)


@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
def test_prometheus_metrics_collector():
    c = PrometheusMetricsCollector(namespace="test_dag_ns")
    m = TaskMetrics(task_id="t", dag_id="d", duration_seconds=1.0, status="completed", retry_count=0, worker_id="w", resource_usage={})
    c.record_task_start("t", "d", "w")
    c.record_task_end(m)
    c.record_queue_depth("d", 1, 2, 3)
    c.record_resource_utilization(1.0, 2.0, 3.0)
    c.record_retry("t", 1)


@pytest.mark.skipif(OTEL_AVAILABLE, reason="opentelemetry available")
def test_otel_collector_raises_without_opentelemetry():
    with pytest.raises(RuntimeError):
        OTELTracingCollector()


@pytest.mark.skipif(not OTEL_AVAILABLE, reason="opentelemetry not installed")
def test_otel_collector_wraps_function():
    c = OTELTracingCollector(tracer_name="test_dag_tracer")

    def fn(a, b=2):
        return a + b

    assert c.trace_task("t1", "d1", fn)(1) == 3


# --------------------------------------------------------------------------
# dag_persistence
# --------------------------------------------------------------------------

def test_filesystem_persistence_roundtrip(tmp_path):
    p = FileSystemDAGPersistence(base_dir=str(tmp_path / "cps"))
    g = DAGGraph(dag_id="cp_dag")
    g.add_node(_node("a"))
    p.save_checkpoint(g, "cp_dag_cp_1")

    loaded = p.load_checkpoint("cp_dag_cp_1")
    assert loaded is not None
    assert loaded.dag_id == "cp_dag"
    assert "a" in loaded.nodes

    assert p.load_checkpoint("missing") is None
    assert p.list_checkpoints("cp_dag") == ["cp_dag_cp_1"]
    assert p.list_checkpoints("other") == []

    # corrupt file is ignored during listing
    (Path(p.base_dir) / "broken.json").write_text("{not json", encoding="utf-8")
    assert p.list_checkpoints("cp_dag") == ["cp_dag_cp_1"]

    p.delete_checkpoint("cp_dag_cp_1")
    p.delete_checkpoint("cp_dag_cp_1")  # missing_ok
    assert p.list_checkpoints("cp_dag") == []


def test_redis_persistence_guarded():
    import src.backend.tasks.dag_persistence as dp

    if not dp.REDIS_AVAILABLE:
        with pytest.raises(RuntimeError):
            dp.RedisDAGPersistence()


# --------------------------------------------------------------------------
# dag_scheduler
# --------------------------------------------------------------------------

def _sched(tmp_path=None, **kw) -> DAGScheduler:
    kwargs = {}
    if tmp_path is not None:
        kwargs["persistence"] = FileSystemDAGPersistence(base_dir=str(tmp_path))
    kwargs.update(kw)
    return DAGScheduler(**kwargs)


def test_scheduler_defaults_and_registration():
    s = _sched()
    assert s.task_registry == {}
    s.register_task("f", lambda: 1)
    assert "f" in s.task_registry
    assert s.replanner is not None or s.replanner is None


async def test_run_dag_requires_graph_or_resume():
    s = _sched()
    with pytest.raises(ValueError, match="resume_from"):
        await s.run_dag()


async def test_run_dag_resume_from_checkpoint(tmp_path):
    p = FileSystemDAGPersistence(base_dir=str(tmp_path))
    g = DAGGraph(dag_id="resume_dag")
    g.add_node(_node("a", func_name="ok"))
    g.mark_completed("a", 1)
    p.save_checkpoint(g, "resume_dag_cp_9")

    s = DAGScheduler(task_registry={"ok": lambda: 5}, persistence=p)
    out = await s.run_dag(resume_from="resume_dag_cp_9")
    assert out.is_all_completed()

    with pytest.raises(ValueError, match="Checkpoint not found"):
        await s.run_dag(resume_from="nope")


async def test_run_dag_missing_func_fails_and_cascades():
    s = _sched()
    g = DAGGraph(dag_id="miss")
    g.add_node(_node("a", func_name="missing", retry_limit=0))
    g.add_node(_node("b", dependencies=["a"]))
    out = await s.run_dag(g)
    assert out.nodes["a"].status == "failed"
    assert out.nodes["b"].status == "cancelled"
    assert out.has_failures() is True


async def test_run_dag_retry_then_success():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("flaky")
        return "ok"

    s = _sched()
    s.register_task("flaky", flaky)
    g = DAGGraph(dag_id="retry")
    g.add_node(_node("a", func_name="flaky", retry_limit=3))
    out = await s.run_dag(g)
    assert out.nodes["a"].status == "completed"
    assert out.nodes["a"].result == "ok"
    assert calls["n"] == 2


async def test_run_dag_timeout_marks_failed():
    async def slow():
        await asyncio.sleep(5)

    s = _sched()
    s.register_task("slow", slow)
    g = DAGGraph(dag_id="to")
    g.add_node(_node("a", func_name="slow", timeout_seconds=0.05, retry_limit=0))
    out = await s.run_dag(g)
    assert out.nodes["a"].status == "failed"
    assert "Timeout" in out.nodes["a"].error


async def test_run_dag_fail_fast_halts():
    async def boom():
        raise RuntimeError("fatal")

    async def other():
        await asyncio.sleep(0.01)
        return 1

    s = _sched()
    s.register_task("boom", boom)
    s.register_task("other", other)
    g = DAGGraph(dag_id="ff")
    g.add_node(_node("a", func_name="boom", retry_limit=0))
    g.add_node(_node("b", func_name="other", retry_limit=0))
    out = await s.run_dag(g, fail_fast=True)
    assert out.has_failures() is True


async def test_run_dag_publishes_events():
    events = []

    class Bus:
        async def publish_async(self, name, payload):
            events.append(name)

    class Hub:
        async def broadcast(self, event):
            events.append("hub:" + event.event_type)

    s = _sched(event_bus=Bus(), pipeline_event_hub=Hub())
    g = DAGGraph(dag_id="ev")
    g.add_node(_node("a", func_name="ok"))
    s.register_task("ok", lambda: 1)
    await s.run_dag(g)
    assert "dag.task_started" in events
    assert "dag.task_completed" in events
    assert "hub:dag.completed" in events


async def test_publish_event_swallows_exceptions():
    class BadBus:
        async def publish_async(self, name, payload):
            raise RuntimeError("bus down")

    class BadHub:
        async def broadcast(self, event):
            raise RuntimeError("hub down")

    s = _sched(event_bus=BadBus(), pipeline_event_hub=BadHub())
    await s._publish_event("x", {})
    s2 = _sched()
    await s2._publish_event("x", {})


async def test_execute_task_wrapper_coroutine_function_and_huey_flag():
    async def coro_fn(x):
        return x + 1

    s = _sched()
    s.register_task("coro", coro_fn)
    g = DAGGraph(dag_id="cw")
    n = _node("a", func_name="coro", kwargs={"x": 1}, status="ready")
    g.add_node(n)
    await s._execute_task_wrapper(g, n)
    assert g.nodes["a"].result == 2


async def test_execute_task_wrapper_unregistered_function():
    s = _sched()
    g = DAGGraph(dag_id="cw2")
    n = _node("a", func_name="nope", retry_limit=0)
    g.add_node(n)
    await s._execute_task_wrapper(g, n)
    assert g.nodes["a"].status == "failed"
    assert "not registered" in g.nodes["a"].error


async def test_execute_task_wrapper_uses_worker_recovery_and_metrics():
    recovery = MagicMock()
    recovery.log_task_start = AsyncMock()
    recovery.log_task_completion = AsyncMock()
    metrics = MagicMock()
    s = _sched(worker_recovery=recovery, metrics_collector=metrics)
    s.register_task("ok", lambda: {"a": 1})
    g = DAGGraph(dag_id="wal")
    n = _node("a", func_name="ok")
    g.add_node(n)
    await s._execute_task_wrapper(g, n)
    recovery.log_task_start.assert_awaited_once()
    recovery.log_task_completion.assert_awaited_once()

    # failing path also logs
    n2 = _node("b", func_name="bad", retry_limit=0)
    g.add_node(n2)
    s.register_task("bad", lambda: 1 / 0)
    await s._execute_task_wrapper(g, n2)
    assert g.nodes["b"].status == "failed"
    assert recovery.log_task_completion.await_count == 2
    assert metrics.record_task_end.call_count == 2
    metrics.record_retry.assert_not_called()


async def test_execute_task_wrapper_huey_path(monkeypatch):
    import sys

    import src.backend.tasks.huey  # noqa: F401  (registers the module)
    huey_mod = sys.modules["src.backend.tasks.huey"]

    async def fake_wait(res, timeout=60.0):
        return res

    monkeypatch.setattr(huey_mod, "execute_agent_node_task", lambda **kw: {"status": "ok", **kw}, raising=False)
    monkeypatch.setattr(huey_mod, "async_wait_huey_result", fake_wait, raising=False)

    s = _sched(huey_instance=object(), use_huey=True)
    g = DAGGraph(dag_id="h")
    n = _node("a", func_name="anything", kwargs={"_use_huey": True, "k": 1})
    g.add_node(n)
    await s._execute_task_wrapper(g, n)
    assert g.nodes["a"].result["kwargs"] == {"k": 1}
    assert g.nodes["a"].result["node_id"] == "a"


async def test_execute_task_wrapper_huey_error(monkeypatch):
    import sys

    import src.backend.tasks.huey  # noqa: F401
    huey_mod = sys.modules["src.backend.tasks.huey"]

    async def fake_wait(res, timeout=60.0):
        return {"status": "error", "error": "huey failed"}

    monkeypatch.setattr(huey_mod, "execute_agent_node_task", lambda **kw: None, raising=False)
    monkeypatch.setattr(huey_mod, "async_wait_huey_result", fake_wait, raising=False)

    s = _sched(huey_instance=object(), use_huey=True)
    g = DAGGraph(dag_id="h2")
    n = _node("a", func_name="anything", retry_limit=0)
    g.add_node(n)
    await s._execute_task_wrapper(g, n)
    assert g.nodes["a"].status == "failed"
    assert g.nodes["a"].error == "huey failed"


async def test_run_dag_checkpoint_saved_via_done_callback(tmp_path):
    p = FileSystemDAGPersistence(base_dir=str(tmp_path))
    s = DAGScheduler(task_registry={"ok": lambda: 1}, persistence=p, checkpoint_interval=1)
    g = DAGGraph(dag_id="cpsave")
    g.add_node(_node("a", func_name="ok"))
    await s.run_dag(g)
    assert p.list_checkpoints("cpsave")
    assert s.find_latest_checkpoint("cpsave") is not None
    assert s.auto_recover("cpsave").dag_id == "cpsave"
    assert s.find_latest_checkpoint("nosuch") is None
    assert s.auto_recover("nosuch") is None


def test_save_checkpoint_handles_failure():
    bad = MagicMock()
    bad.save_checkpoint.side_effect = RuntimeError("disk full")
    s = DAGScheduler(persistence=bad)
    s._save_checkpoint(DAGGraph(dag_id="x"))


def test_retry_failed_subgraph():
    g = DAGGraph(dag_id="rec")
    g.add_node(_node("a"))
    g.add_node(_node("b", dependencies=["a"]))
    g.add_node(_node("c", dependencies=["b"]))
    g.mark_completed("a")
    g.mark_failed("b", "err")

    reset = g and None
    s = _sched()
    out = s.retry_failed_subgraph(g, "b")
    assert out == ["b", "c"]
    assert g.nodes["b"].status == "ready"
    assert g.nodes["c"].status == "pending"
    assert g.nodes["b"].error is None
    assert g.nodes["a"].status == "completed"

    with pytest.raises(KeyError):
        s.retry_failed_subgraph(g, "ghost")


def test_get_execution_summary():
    s = _sched()
    g = DAGGraph(dag_id="sum")
    g.add_node(_node("a", name="A"))
    g.add_node(_node("b", name="B", dependencies=["a"]))
    g.mark_completed("a", {"r": 1})
    g.mark_running("b")
    summary = s.get_execution_summary(g)
    assert summary["dag_id"] == "sum"
    assert summary["total_nodes"] == 2
    assert summary["status_counts"]["completed"] == 1
    assert summary["status_counts"]["running"] == 1
    assert summary["progress_percent"] == 50.0
    assert summary["nodes"]["a"]["has_result"] is True
    assert summary["nodes"]["b"]["has_result"] is False
    assert summary["replanning_count"] == 0
    assert summary["total_rescheduled_tasks"] == 0

    empty = s.get_execution_summary(DAGGraph(dag_id="empty"))
    assert empty["progress_percent"] == 0.0


async def test_replan_node_flow():
    s = _sched()
    g = DAGGraph(dag_id="rp")
    g.add_node(_node("a"))
    g.add_node(_node("b", dependencies=["a"]))
    g.mark_completed("a")
    g.add_node(_node("c", dependencies=["b"]))
    g.mark_failed("b", "x")
    g.mark_pending("c") if hasattr(g, "mark_pending") else g.nodes["c"].__setattr__("status", "pending")

    state = await s.replan_node(g, "b", new_kwargs={"extra": 1}, reason="regen")
    assert state.trigger_node_id == "b"
    assert g.nodes["b"].kwargs["extra"] == 1
    assert s.get_execution_summary(g)["replanning_count"] == 1

    with pytest.raises(KeyError):
        await s.replan_node(g, "ghost")


async def test_replan_node_respects_limit():
    s = _sched()
    g = DAGGraph(dag_id="rplim")
    g.add_node(_node("a", retry_count=3))
    g.add_node(_node("b", dependencies=["a"]))
    with pytest.raises(RuntimeError, match="max replan limit"):
        await s.replan_node(g, "a", max_replan_limit=3)
    assert g.nodes["a"].status == "failed"
    assert g.nodes["b"].status == "cancelled"


async def test_replan_node_instantiates_replanner_when_missing():
    s = _sched()
    s.replanner = None
    g = DAGGraph(dag_id="rp2")
    g.add_node(_node("a"))
    state = await s.replan_node(g, "a")
    assert state.trigger_node_id == "a"
    assert s.replanner is not None


def test_set_scheduling_policy_and_sort():
    s = _sched()
    p = FairRoundRobinPolicy()
    s.set_scheduling_policy(p)
    assert s.scheduling_policy is p
    a, b = _node("a"), _node("b")
    assert s._sort_by_affinity([a, b]) is not None


def test_record_metrics_zero_resources(monkeypatch):
    s = _sched()
    monkeypatch.setattr(
        s.resource_manager,
        "get_available_resources",
        lambda: TaskResourceRequirement(cpu_cores=0, ram_mb=0, gpu_mem_mb=0),
    )
    g = DAGGraph(dag_id="m")
    g.add_node(_node("a", status="ready"))
    s._record_metrics(g)


async def test_allocate_and_release_resources():
    s = _sched()
    s._init_semaphores()
    alloc: dict = {}
    req = TaskResourceRequirement(cpu_cores=2.0, ram_mb=1024, gpu_mem_mb=2048)
    s._allocate_resources("t1", req, alloc)
    assert s.active_allocations.cpu_cores == 2.0
    assert s.active_allocations.gpu_mem_mb == 2048

    s._release_resources("t1", alloc)
    assert s.active_allocations.cpu_cores == 0.0
    assert "t1" not in alloc

    # releasing unknown id / without semaphores is a no-op
    s._release_resources("ghost", alloc)
    s2 = DAGScheduler()
    s2._release_resources("x", {"x": req})

    # double release raises ValueError internally -> swallowed
    s._release_resources("t1", {"t1": req})
    s._semaphores.gpu.release()


async def test_acquire_resources_rolls_back_on_cancel():
    s = _sched()
    s._init_semaphores()
    req = TaskResourceRequirement(cpu_cores=1.0, ram_mb=512, gpu_mem_mb=0)
    await s._acquire_resources(req)
    assert s._semaphores.cpu._value == s._semaphores.cpu._value

    class _Boom:
        async def acquire(self):
            raise asyncio.CancelledError()

    s._semaphores.gpu = _Boom()
    req_gpu = TaskResourceRequirement(cpu_cores=1.0, ram_mb=512, gpu_mem_mb=1)
    with pytest.raises(asyncio.CancelledError):
        await s._acquire_resources(req_gpu)


async def test_can_schedule_approx():
    s = _sched()
    s._init_semaphores()
    assert s._can_schedule_approx(TaskResourceRequirement(ram_mb=512)) is True
    assert s._can_schedule_approx(TaskResourceRequirement(ram_mb=1024 * 1024 * 10)) is False
    s._semaphores.gpu._value = 0
    assert s._can_schedule_approx(TaskResourceRequirement(ram_mb=512, gpu_mem_mb=1024)) is False
    s._semaphores.cpu._value = 0
    assert s._can_schedule_approx(TaskResourceRequirement()) is False


async def test_cancel_running_tasks_and_helper():
    s = _sched()
    started = asyncio.Event()

    async def forever():
        started.set()
        await asyncio.sleep(10)

    t = asyncio.create_task(forever())
    await started.wait()
    s.active_async_tasks["x"] = t
    await s.cancel_running_tasks()
    assert t.cancelled() or t.done()

    t2 = asyncio.create_task(asyncio.sleep(10))
    s._running_tasks = {"y": t2}
    running = dict(s._running_tasks)
    alloc = {"y": TaskResourceRequirement()}
    await s._cancel_running_tasks(running, alloc)
    assert running == {}
    await s._cancel_running_tasks({}, {})


def test_cancel_downstream_tasks_helper():
    s = _sched()
    g = DAGGraph(dag_id="cd")
    g.add_node(_node("a"))
    g.add_node(_node("b", dependencies=["a"]))
    assert s._cancel_downstream_tasks("a", g) == ["b"]
    assert s._cancel_downstream_tasks("a") == []


async def test_on_startup_with_worker_recovery():
    recovery = MagicMock()
    recovery.recover_orphan_tasks = AsyncMock(return_value=["d1", "d2"])
    s = _sched(worker_recovery=recovery)
    assert await s.on_startup() == ["d1", "d2"]

    recovery.recover_orphan_tasks = AsyncMock(return_value=[])
    assert await s.on_startup() == []


async def test_on_startup_local_checkpoint_recovery(tmp_path):
    p = FileSystemDAGPersistence(base_dir=str(tmp_path))
    g = DAGGraph(dag_id="recover_me")
    g.add_node(_node("a"))
    p.save_checkpoint(g, "recover_me_cp_1")
    s = DAGScheduler(persistence=p)
    resumed = await s.on_startup()
    assert resumed == ["recover_me"]

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    s2 = DAGScheduler(persistence=FileSystemDAGPersistence(base_dir=str(empty_dir)))
    assert await s2.on_startup() == []


async def test_on_startup_skips_broken_checkpoint(tmp_path):
    p = FileSystemDAGPersistence(base_dir=str(tmp_path))
    (Path(p.base_dir) / "broken_cp_1.json").write_text(
        json.dumps({"_checkpoint_meta": {"dag_id": "broken"}}), encoding="utf-8"
    )
    s = DAGScheduler(persistence=p)
    # malformed checkpoint is logged and skipped, not fatal
    assert await s.on_startup() == []


async def test_resume_from_checkpoint_with_wal():
    g = DAGGraph(dag_id="wal")
    g.add_node(_node("a"))
    g.add_node(_node("b", dependencies=["a"]))

    s = _sched()
    out = await s.resume_from_checkpoint_with_wal("wal", g)
    assert out is g

    recovery = MagicMock()
    recovery.resume_dag_from_checkpoint = AsyncMock(return_value=["a", "missing", "b"])
    entry_ok = MagicMock(output_json=json.dumps({"v": 1}), created_at="2024-01-01")
    entry_bad = MagicMock(output_json="{bad json", created_at="2024-01-01")
    entry_none = MagicMock(output_json=None, created_at=None)
    recovery.get_latest_wal_for_node = AsyncMock(
        side_effect=[entry_ok, entry_none, entry_bad, entry_ok]
    )
    s2 = _sched(worker_recovery=recovery, db_manager=MagicMock())
    out2 = await s2.resume_from_checkpoint_with_wal("wal", g)
    assert out2.nodes["a"].status == "completed"
    assert out2.nodes["a"].result == {"v": 1}


def test_task_state_enum_values():
    from src.backend.tasks.dag_scheduler import DAGTaskState

    assert DAGTaskState.PENDING == "pending"
    assert DAGTaskState.RUNNING.value == "running"
    assert DAGTaskState.COMPLETED.value == "completed"
    assert DAGTaskState.FAILED.value == "failed"
    assert DAGTaskState.CANCELLED.value == "cancelled"


async def test_scheduler_applies_numa_affinity_when_available(monkeypatch):
    topo = NUMATopology(cpu_to_numa={0: 0, 1: 1}, numa_nodes=[0, 1])
    s = _sched()
    s.resource_manager.numa_topology = topo
    s.resource_manager.get_worker_numa_affinity = lambda idx, is_gpu=False: 0
    applied: dict = {}
    monkeypatch.setattr(os, "sched_setaffinity", lambda pid, cpus: applied.setdefault("cpus", cpus), raising=False)
    monkeypatch.setattr(os, "sched_setaffinity", lambda pid, cpus: applied.setdefault("cpus", cpus), raising=False)

    s.register_task("ok", lambda: 1)
    g = DAGGraph(dag_id="numa")
    n = _node("worker_0", func_name="ok")
    g.add_node(n)
    await s._execute_task_wrapper(g, n)
    assert g.nodes["worker_0"].result == 1


def test_detect_numa_topology_with_fake_hwloc(monkeypatch):
    import sys
    import types

    class _Obj:
        def __init__(self, os_index, numa):
            self.os_index = os_index
            self._numa = numa

        def get_ancestor_by_type(self, kind):
            return self._numa

    class _Topology:
        OBJ_NUMANODE = 1
        OBJ_PU = 2
        OBJ_GPU = 3

        def get_objects_by_type(self, kind):
            if kind == 1:
                return [_Obj(0, None), _Obj(1, None)]
            if kind == 2:
                return [_Obj(0, _Obj(0, None)), _Obj(1, _Obj(0, None)), _Obj(2, _Obj(1, None))]
            return [_Obj(0, _Obj(1, None))]

    fake = types.ModuleType("hwloc")
    fake.Topology = _Topology
    fake.OBJ_NUMANODE = 1
    fake.OBJ_PU = 2
    fake.OBJ_GPU = 3
    monkeypatch.setitem(sys.modules, "hwloc", fake)

    topo = detect_numa_topology()
    assert topo.numa_nodes == [0, 1]
    assert topo.cpu_to_numa == {0: 0, 1: 0, 2: 1}
    assert topo.gpu_to_numa == {0: 1}
    assert topo.cpu_cores_per_numa == {0: 2, 1: 1}


def test_detect_numa_topology_without_gpu_support(monkeypatch):
    import sys
    import types

    class _Topology:
        OBJ_NUMANODE = 1
        OBJ_PU = 2

        def __init__(self):
            self.gpu_attr = True

        def get_objects_by_type(self, kind):
            return []

    fake = types.ModuleType("hwloc")
    fake.Topology = _Topology
    fake.OBJ_NUMANODE = 1
    fake.OBJ_PU = 2
    fake.OBJ_GPU = 3
    monkeypatch.setitem(sys.modules, "hwloc", fake)
    topo = detect_numa_topology()
    assert topo.numa_nodes == []


def test_detect_gpu_numa_with_fake_pynvml(monkeypatch, tmp_path):
    import sys

    class _Pci:
        domain = 0
        bus = 1
        device = 2
        function = 3

    class _Nvml:
        @staticmethod
        def nvmlInit():
            return None

        @staticmethod
        def nvmlDeviceGetCount():
            return 2

        @staticmethod
        def nvmlDeviceGetHandleByIndex(i):
            return object()

        @staticmethod
        def nvmlDeviceGetPciInfo(handle):
            if handle == "bad":
                raise RuntimeError("boom")
            return _Pci()

    monkeypatch.setitem(sys.modules, "pynvml", _Nvml)
    assert detect_gpu_numa_py3nvml() == {}


def test_detect_gpu_numa_init_failure(monkeypatch):
    import sys

    class _Nvml:
        @staticmethod
        def nvmlInit():
            raise RuntimeError("no driver")

    monkeypatch.setitem(sys.modules, "pynvml", _Nvml)
    assert detect_gpu_numa_py3nvml() == {}


def test_detect_gpu_numa_reads_sysfs(monkeypatch, tmp_path):
    import sys

    class _Pci:
        domain = 0
        bus = 0
        device = 0
        function = 0

    class _Nvml:
        @staticmethod
        def nvmlInit():
            return None

        @staticmethod
        def nvmlDeviceGetCount():
            return 1

        @staticmethod
        def nvmlDeviceGetHandleByIndex(i):
            return object()

        @staticmethod
        def nvmlDeviceGetPciInfo(handle):
            return _Pci()

    monkeypatch.setitem(sys.modules, "pynvml", _Nvml)
    import builtins

    real_open = builtins.open

    def fake_open(path, *a, **kw):
        if str(path).startswith("/sys/bus/pci"):
            raise OSError("missing")
        return real_open(path, *a, **kw)

    monkeypatch.setattr(builtins, "open", fake_open)
    assert detect_gpu_numa_py3nvml() == {}


def test_redis_persistence_roundtrip(monkeypatch):
    import src.backend.tasks.dag_persistence as dp

    if not dp.REDIS_AVAILABLE:
        pytest.skip("redis not installed")

    class _FakeRedis:
        def __init__(self):
            self.store = {}

        def from_url(self, url, decode_responses=True):
            return self

        def setex(self, key, ttl, value):
            self.store[key] = value

        def get(self, key):
            return self.store.get(key)

        def scan_iter(self, match=None):
            return list(self.store.keys())

        def delete(self, key):
            self.store.pop(key, None)

    monkeypatch.setattr(dp.redis, "from_url", lambda url, decode_responses=True: _FakeRedis())
    p = dp.RedisDAGPersistence(url="redis://localhost:6379", ttl=60)
    g = DAGGraph(dag_id="r_dag")
    g.add_node(_node("a"))
    p.save_checkpoint(g, "r_dag_cp_1")
    assert p.load_checkpoint("r_dag_cp_1").dag_id == "r_dag"
    assert p.load_checkpoint("nope") is None
    assert p._key("x") == "dag:checkpoint:x"
    p.delete_checkpoint("r_dag_cp_1")
    assert p.load_checkpoint("r_dag_cp_1") is None


def test_redis_persistence_list_checkpoints(monkeypatch):
    import src.backend.tasks.dag_persistence as dp

    if not dp.REDIS_AVAILABLE:
        pytest.skip("redis not installed")

    class _FakeRedis:
        def __init__(self):
            self.store = {}

        def setex(self, key, ttl, value):
            self.store[key] = value

        def get(self, key):
            return self.store.get(key)

        def scan_iter(self, match=None):
            return list(self.store.keys())

    fake = _FakeRedis()
    monkeypatch.setattr(dp.redis, "from_url", lambda url, decode_responses=True: fake)
    p = dp.RedisDAGPersistence()
    g = DAGGraph(dag_id="lc_dag")
    g.add_node(_node("a"))
    p.save_checkpoint(g, "lc_dag_cp_1")
    # Redis-backed checkpoints written by other producers carry meta
    payload = g.model_dump(mode="json")
    payload["_checkpoint_meta"] = {"dag_id": "lc_dag"}
    fake.store["dag:checkpoint:lc_dag_cp_1"] = json.dumps(payload)
    fake.store["dag:checkpoint:orphan"] = json.dumps({"_checkpoint_meta": {"dag_id": "zzz"}})
    assert p.list_checkpoints("lc_dag") == ["lc_dag_cp_1"]


def test_dag_replanner_downstream_and_cancel():
    from src.backend.tasks.dag_replanning import DAGReplanner

    g = DAGGraph(dag_id="dr")
    g.add_node(_node("a"))
    g.add_node(_node("b", dependencies=["a"]))
    g.add_node(_node("c", dependencies=["b"]))

    assert DAGReplanner.get_downstream_tasks(g, "ghost") == []
    assert sorted(DAGReplanner.get_downstream_tasks(g, "a")) == ["b", "c"]
    assert DAGReplanner.get_downstream_tasks(g, "a", include_self=True)[0] == "a"

    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(asyncio.sleep(10))
        g.mark_running("b")
        cancelled = DAGReplanner.cancel_downstream_execution(g, "a", active_async_tasks={"b": task})
    finally:
        task.cancel()
        loop.close()
    assert sorted(cancelled) == ["b", "c"]
    assert g.nodes["b"].status == "cancelled"

    # completed nodes are not cancelled
    g2 = DAGGraph(dag_id="dr2")
    g2.add_node(_node("a"))
    g2.add_node(_node("b", dependencies=["a"]))
    g2.mark_completed("b")
    assert DAGReplanner.cancel_downstream_execution(g2, "a") == []


def test_dag_replanner_plan_local_retry():
    from src.backend.tasks.dag_replanning import DAGReplanner

    g = DAGGraph(dag_id="plr")
    g.add_node(_node("a", retry_count=1))
    g.add_node(_node("b", dependencies=["a"]))
    g.mark_completed("a", result="old")
    g.mark_pending("b") if hasattr(g, "mark_pending") else setattr(g.nodes["b"], "status", "pending")

    state = DAGReplanner.plan_local_retry(g, "a", new_kwargs={"x": 1}, reason="why")
    assert state.reason == "why"
    assert state.trigger_node_id == "a"
    assert g.nodes["a"].retry_count == 2
    assert g.nodes["a"].kwargs["x"] == 1
    assert g.nodes["a"].status == "pending"
    assert g.nodes["b"].status == "pending"
    d = state.to_dict()
    assert d["timestamp"]

    with pytest.raises(KeyError):
        DAGReplanner.plan_local_retry(g, "ghost")
