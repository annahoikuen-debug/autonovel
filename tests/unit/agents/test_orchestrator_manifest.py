"""src/agents/orchestrator.py の from_manifest 周辺テスト."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.agents.orchestrator import AgentContext, AgentName, CyclicDependencyError, Orchestrator


MODULE = "tests.fake_manifest_skills"


@pytest.fixture
def skill_module(tmp_path, monkeypatch):
    path = Path(__file__).with_name("fake_manifest_skills.py")
    assert path.exists()
    if str(tmp_path) not in __import__("sys").path:
        monkeypatch.syspath_prepend(str(tmp_path.parent))
    return path


def _write_manifest(tmp_path: Path, body: str) -> str:
    p = tmp_path / "manifest.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(p)


def test_from_manifest_orders_and_wires_nodes(tmp_path):
    manifest = _write_manifest(
        tmp_path,
        """
        skills:
          - name: second
            class: tests.fake_manifest_skills.SecondSkill
            depends_on: [first]
          - name: first
            class: tests.fake_manifest_skills.FirstSkill
            config:
              marker: "from-config"
        """,
    )
    orch = Orchestrator.from_manifest(manifest)
    assert orch._ordered_skill_names == ["first", "second"]
    assert "first" in orch.nodes
    assert "second" in orch.nodes
    # 短縮名と AgentName エイリアスも登録される
    assert orch.nodes["second"] is orch.nodes["second"]


async def test_from_manifest_run_executes_in_order(tmp_path):
    manifest = _write_manifest(
        tmp_path,
        """
        skills:
          - name: first
            class: tests.fake_manifest_skills.FirstSkill
          - name: second
            class: tests.fake_manifest_skills.SecondSkill
            depends_on: [first]
        """,
    )
    orch = Orchestrator.from_manifest(manifest)
    ctx = await orch.run(AgentContext(1, 1, 1))
    assert ctx.artifacts["order"] == ["first", "second"]


async def test_from_manifest_node_sets_next_agent(tmp_path):
    manifest = _write_manifest(
        tmp_path,
        """
        skills:
          - name: first
            class: tests.fake_manifest_skills.FirstSkill
          - name: second
            class: tests.fake_manifest_skills.SecondSkill
            depends_on: [first]
        """,
    )
    orch = Orchestrator.from_manifest(manifest)
    node = orch.nodes["first"]
    from src.agents.orchestrator import AgentContext as C

    res = await node(C(1, 1, 1))
    assert res.next_agent == "second"


def test_from_manifest_skips_disabled_skills(tmp_path):
    manifest = _write_manifest(
        tmp_path,
        """
        skills:
          - name: first
            class: tests.fake_manifest_skills.FirstSkill
          - name: second
            class: tests.fake_manifest_skills.SecondSkill
            config:
              enabled: false
        """,
    )
    orch = Orchestrator.from_manifest(manifest)
    assert orch._ordered_skill_names == ["first"]


def test_from_manifest_uses_runs_after_and_runs_before(tmp_path):
    manifest = _write_manifest(
        tmp_path,
        """
        skills:
          - name: a
            class: tests.fake_manifest_skills.FirstSkill
            runs_before: [b]
          - name: b
            class: tests.fake_manifest_skills.SecondSkill
            runs_after: [a]
        """,
    )
    orch = Orchestrator.from_manifest(manifest)
    assert orch._ordered_skill_names == ["a", "b"]


def test_from_manifest_ignores_unknown_dependencies(tmp_path):
    manifest = _write_manifest(
        tmp_path,
        """
        skills:
          - name: a
            class: tests.fake_manifest_skills.FirstSkill
            depends_on: [ghost]
            runs_after: [ghost2]
        """,
    )
    orch = Orchestrator.from_manifest(manifest)
    assert orch._ordered_skill_names == ["a"]


def test_from_manifest_cyclic_raises(tmp_path):
    manifest = _write_manifest(
        tmp_path,
        """
        skills:
          - name: a
            class: tests.fake_manifest_skills.FirstSkill
            depends_on: [b]
          - name: b
            class: tests.fake_manifest_skills.SecondSkill
            depends_on: [a]
        """,
    )
    with pytest.raises(CyclicDependencyError):
        Orchestrator.from_manifest(manifest)


def test_from_manifest_registers_agent_name_enum_key(tmp_path):
    manifest = _write_manifest(
        tmp_path,
        """
        skills:
          - name: PlanningAgent
            class: tests.fake_manifest_skills.FirstSkill
        """,
    )
    orch = Orchestrator.from_manifest(manifest)
    assert AgentName.PLANNING in orch.nodes


def test_from_manifest_registers_with_dag_scheduler(tmp_path):
    manifest = _write_manifest(
        tmp_path,
        """
        skills:
          - name: first
            class: tests.fake_manifest_skills.FirstSkill
        """,
    )
    dag = MagicMock()
    orch = Orchestrator.from_manifest(manifest, dag_scheduler=dag, use_dag_scheduler=True)
    dag.register_task.assert_called_once()


def test_from_manifest_passes_dependencies(tmp_path):
    manifest = _write_manifest(
        tmp_path,
        """
        skills:
          - name: first
            class: tests.fake_manifest_skills.FirstSkill
        """,
    )
    orch = Orchestrator.from_manifest(manifest, dependencies={"repo": "REPO"})
    assert orch._skill_instances["first"].repo == "REPO"
