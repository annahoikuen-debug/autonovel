"""Step 10 (H9): タスク投入前に task_id を付与し DB 行を先に作成する。

H9: easy_mode.py は Huey 投入後に task_result.id から task_id を取得していたが、
Huey は enqueue 時に引数をシリアライズするためワーカー側 task_id=None になり、
DB 行が永遠に "running" のままになっていた。修正：
- Huey 投入前に uuid で task_id を生成し params に設定
- DB 行を先に作成してからタスクをエンキュー
"""
from __future__ import annotations

import inspect

from src.backend.routers import easy_mode


def test_task_id_set_before_huey_enqueue():
    """params["task_id"] が generate_chapter_orchestrated_task 投入前に設定されている（H9）。"""
    src = inspect.getsource(easy_mode)
    # task_id 生成が generate_chapter_orchestrated_task 呼び出しより前にある
    task_id_gen_pos = src.find("huey_task_id = str(uuid.uuid4())")
    enqueue_pos = src.find("task_result = generate_chapter_orchestrated_task(params)")
    assert task_id_gen_pos != -1, "uuid.uuid4() による task_id 生成がない (H9)"
    assert enqueue_pos != -1, "generate_chapter_orchestrated_task 呼び出しがない (H9)"
    assert task_id_gen_pos < enqueue_pos, "task_id 生成が Huey エンキューより後になっている (H9)"
    # params に task_id を設定している
    assert 'params["task_id"] = huey_task_id' in src
    # DB レコード作成がエンキューより前にある
    create_task_pos = src.find("create_task_async(task_id=huey_task_id")
    assert create_task_pos != -1, "create_task_async 呼び出しがない (H9)"
    assert create_task_pos < enqueue_pos, "DB 行作成が Huey エンキューより後になっている (H9)"
