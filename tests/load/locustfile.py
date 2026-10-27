"""AutoNovel 負荷試験用 Locust スクリプト。

**これはテストではない。** ファイル名を ``test_*.py`` にすると pytest の
``python_files`` に一致し収集対象になる。その状態で収集すると
``import locust`` が ``ssl`` を monkey-patch する（gevent 経由）ため、
ssl を先に import 済みのセッションでは ``RecursionError`` で収集が落ちる。
実行には ``locust -f tests/load/locustfile.py --host http://localhost:8200`` を使う。

対象エンドポイントは実 API に合わせてある:
  POST /api/novel/produce              → 作品全話生成を開始（api_key 必須）
  GET  /api/novel/{project_id}/status   → ステータス照会
  GET  /api/novel/{project_id}/episodes → 話数一覧
"""

import os
import random

from locust import HttpUser, between, task

API_KEY = os.environ.get("AUTONOVEL_API_KEY", "")
GENRES = ["fantasy", "sci-fi", "romance", "mystery", "horror"]


class NovelPipelineUser(HttpUser):
    """制作パイプライン全体の負荷を測るユーザー。"""

    wait_time = between(1, 5)
    host = os.environ.get("AUTONOVEL_HOST", "http://localhost:8200")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if API_KEY:
            headers["X-API-Key"] = API_KEY
        return headers

    @task
    def produce_and_poll(self) -> None:
        project_id = self._create_project()
        if project_id is None:
            return
        self._poll_status(project_id)
        self._list_episodes(project_id)

    def _create_project(self) -> int | None:
        payload = {
            "title": f"LoadTest-{random.randint(1, 100000)}",
            "genre": random.choice(GENRES),
            "synopsis": "負荷試験用の自動生成糙です。",
            "target_episodes": random.choice([1, 3, 5]),
            "target_word_count": 1000,
        }
        with self.client.post(
            "/api/novel/produce",
            json=payload,
            headers=self._headers(),
            catch_response=True,
            name="POST /api/novel/produce",
        ) as response:
            if response.status_code in (200, 201, 202):
                project_id = response.json().get("project_id")
                if project_id is not None:
                    return int(project_id)
            response.failure(f"作品作成に失敗: {response.status_code} {response.text[:200]}")
            return None

    def _poll_status(self, project_id: int) -> None:
        for _ in range(10):
            with self.client.get(
                f"/api/novel/{project_id}/status",
                name="GET /api/novel/{id}/status",
            ) as response:
                if response.status_code != 200:
                    response.failure(f"status 取得に失敗: {response.status_code}")
                    return
                status = response.json().get("status")
                if status in {"completed", "failed", "error"}:
                    return

    def _list_episodes(self, project_id: int) -> None:
        with self.client.get(
            f"/api/novel/{project_id}/episodes",
            name="GET /api/novel/{id}/episodes",
        ) as response:
            if response.status_code != 200:
                response.failure(f"episodes 取得に失敗: {response.status_code}")
