"""Task state helper functions."""

import json
import time

from src.core.container import AppContainer


async def create_task(
    task_id: str,
    message: str,
    total_steps: int = 1,
    user_id: int | None = None,
) -> None:
    """タスクの初期状態をDBに保存する。

    `user_id` はこのタスクを所有するユーザーの ID。
    `GET /api/tasks/{task_id}/status` などの所有権判定に使用されるため、
    呼び出し側は必ず現在ユーザーを渡すこと。
    """
    db = AppContainer.db()
    initial_state = {
        "is_running": True,
        "user_id": user_id,
        "current_step": 0,
        "total_steps": total_steps,
        "message": message,
        "sub_message": "キューの待機中",
        "streaming_text": "",
        "logs": [f"[{time.strftime('%H:%M:%S')}] 🚀 タスクを登録しました。"],
        "error": None,
        "result_data": None,
        "token_usage": {"prompt": 0, "completion": 0, "calls": 0},
        "start_time": time.time(),
        "last_updated": time.time(),
    }
    await db.save_internal_state(
        f"task_status:{task_id}", json.dumps(initial_state), time.strftime("%Y-%m-%d %H:%M:%S")
    )
