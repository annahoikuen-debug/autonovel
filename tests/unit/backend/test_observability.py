"""src/backend/observability/health.py の単体テスト。"""

from __future__ import annotations

import threading

import pytest

from src.backend.observability.health import _Metrics, metrics


class TestMetrics:
    """_Metrics クラスの単体テスト。"""

    def test_increment_and_snapshot(self):
        """カウンタを増やし、スナップショットで取得できること。"""
        m = _Metrics()
        m.increment("tasks_enqueued", 5)
        m.increment("tasks_completed", 3)

        snap = m.snapshot()
        assert snap["tasks_enqueued"] == 5
        assert snap["tasks_completed"] == 3
        assert snap["tasks_failed"] == 0
        assert snap["exports_attempted"] == 0
        assert snap["exports_succeeded"] == 0
        assert snap["health_checks"] == 0

    def test_increment_unknown_name_ignored(self):
        """未定義名へのインクリメントは無視されること。"""
        m = _Metrics()
        m.increment("unknown_counter", 999)

        snap = m.snapshot()
        assert snap["tasks_enqueued"] == 0
        assert snap["tasks_completed"] == 0

    def test_increment_key_too_long_ignored(self):
        """64文字を超えるキーは無視されること。"""
        m = _Metrics()
        m.increment("a" * 65, 5)

        snap = m.snapshot()
        assert all(v == 0 for v in snap.values())

    def test_get(self):
        """get で個別カウンタを取得できること。"""
        m = _Metrics()
        m.increment("tasks_enqueued", 7)

        assert m.get("tasks_enqueued") == 7
        assert m.get("unknown") == 0

    def test_reset(self):
        """全カウンタを 0 に戻せること。"""
        m = _Metrics()
        m.increment("tasks_enqueued", 5)
        m.increment("tasks_completed", 3)
        m.reset()

        snap = m.snapshot()
        assert snap["tasks_enqueued"] == 0
        assert snap["tasks_completed"] == 0
        assert snap["tasks_failed"] == 0

    def test_thread_safety(self):
        """複数スレッドからのインクリメントが競合せず正しく集計されること。"""
        m = _Metrics()
        errors: list[Exception] = []

        def worker() -> None:
            try:
                for _ in range(1000):
                    m.increment("tasks_enqueued")
            except Exception as exc:  # noqa: BLE001 - テスト用に捕捉
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert m.snapshot()["tasks_enqueued"] == 10_000


class TestGlobalMetricsInstance:
    """モジュール単一インスタンス metrics のテスト。"""

    def test_metrics_instance_exists(self):
        """metrics インスタンスが存在し、スナップショットが取得できること。"""
        assert metrics is not None
        snap = metrics.snapshot()
        assert isinstance(snap, dict)
        assert "tasks_enqueued" in snap
