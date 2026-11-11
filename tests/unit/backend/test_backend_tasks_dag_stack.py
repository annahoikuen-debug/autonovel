"""Coverage tests for src/backend/tasks DAG stack (models, engine, policies, numa, resources, metrics, persistence, scheduler)."""
from __future__ import annotations

import pytest

from src.backend.tasks.dag_models import DAGTaskNode


def test_dag_task_node_creation_minimal():
    """DAGTaskNode の最小構成コンストラクタ確認テスト。"""
    node = DAGTaskNode(task_id="minimal", name="minimal", func_name="run")
    assert node.task_id == "minimal"
    assert node.name == "minimal"


def test_dag_task_node_creation_with_deps():
    """DAGTaskNode に依存関係を持たせたコンストラクタ確認テスト。"""
    node = DAGTaskNode(
        task_id="node_with_deps",
        name="node_with_deps",
        func_name="execute",
        dependencies=["parent1"],
    )
    assert node.task_id == "node_with_deps"
    assert node.name == "node_with_deps"
    assert node.dependencies == ["parent1"]
    assert node.func_name == "execute"


def test_dag_task_node_resources_default():
    """DAGTaskNode の resources フィールドのデフォルト値確認テスト。"""
    node = DAGTaskNode(task_id="resources_test", name="resources_test", func_name="run")
    # resources は TaskResourceRequirement のインスタンスであることを確認
    assert node.resources.cpu_cores == 1.0
    assert node.resources.gpu_mem_mb == 0
    assert node.resources.ram_mb == 512
