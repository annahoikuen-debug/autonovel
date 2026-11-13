"""Step 13 (H12): Zombie 復旧の TOCTOU とマルチワーカー heartbeat 問題を修正。

H12: WorkerRecoveryManager が全 running タスクの heartbeat を更新し、
detect_zombie_tasks とリセットが別セッションのため、クラッシュしたワーカーの
タスクが永遠に復旧されず、かつ完了済みタスクを再実行し得た。
修正：
- update_running_task_heartbeats が自分の worker_id のタスクのみを更新
- recover_orphan_tasks が単一トランザクションの UPDATE で原子的にリセット
"""
from __future__ import annotations

import inspect

from src.backend.tasks.worker_recovery import WorkerRecoveryManager


def test_heartbeat_updates_own_tasks_only():
    """update_running_task_heartbeats が自分の worker_id のタスクのみを更新（H12）。"""
    src = inspect.getsource(WorkerRecoveryManager.update_running_task_heartbeats)
    assert "worker_id == self.worker_id" in src, (
        "update_running_task_heartbeats が他ワーカーのタスクも更新している (H12)"
    )


def test_recover_orphan_uses_single_transaction_update():
    """recover_orphan_tasks が単一トランザクションの UPDATE で原子的にリセット（H12）。"""
    src = inspect.getsource(WorkerRecoveryManager.recover_orphan_tasks)
    assert "update(TaskWALLogModel)" in src, (
        "recover_orphan_tasks が単一 UPDATE を使っていない (H12)"
    )
    assert "worker_id != self.worker_id" in src, (
        "recover_orphan_tasks が自分のタスクを対象外にしていない (H12)"
    )
    assert "await self.detect_zombie_tasks()" not in src, (
        "recover_orphan_tasks が別セッションの detect_zombie_tasks を呼んでいる (H12)"
    )
