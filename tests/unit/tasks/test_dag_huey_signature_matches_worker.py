"""Step 11 (H10): DAG Huey タスク署名の不整合修正。

H10: dag_scheduler.py は execute_agent_node_task(func_name=..., kwargs=..., node_id=...)
で投入していたが、ワーカー src/backend/tasks/huey.py は (node_name, payload)
なので TypeError で必ず失敗していた。修正：node_name=..., payload=... に統一。
"""
from __future__ import annotations

import inspect

from src.backend.tasks.dag_scheduler import DAGScheduler
from src.backend.tasks.huey import execute_agent_node_task


def test_huey_worker_signature_is_node_name_payload():
    """Huey ワーカー execute_agent_node_task の署名が (node_name, payload) である（H10）。
    @huey.task デコレータで inspect.signature がラップされるため、ソースで検査。
    """
    src = inspect.getsource(execute_agent_node_task.func)
    assert "def execute_agent_node_task(" in src
    assert "node_name: str" in src
    assert "payload: dict[str, Any]" in src


def test_dag_scheduler_uses_worker_signature():
    """DAGスケジューラが Huey ワーカーの署名に合わせて投入している（H10）。"""
    src = inspect.getsource(DAGScheduler)
    # Huey パスで node_name= / payload= を使っている
    assert "node_name=task_node.func_name" in src
    assert "payload=clean_kwargs" in src
    # Huey パスで func_name= / kwargs= / node_id= の旧呼び出しが残っていない
    huey_block = src[src.find("should_use_huey"):src.find("timeout_val = task_node.timeout_seconds")]
    assert "func_name=task_node.func_name" not in huey_block
    assert "kwargs=clean_kwargs" not in huey_block
    assert "node_id=task_node.task_id" not in huey_block
