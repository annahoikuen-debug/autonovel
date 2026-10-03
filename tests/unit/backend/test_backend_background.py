"""Coverage tests for src/backend/background.py (progress state, reporters, task manager)."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

import src.backend.background as bg
from src.backend.background import (
    AsyncDbSaveStrategy,
    BackgroundReporter,
    BackgroundTaskManager,
    NoOpSaveStrategy,
    ProgressState,
    RedisSaveStrategy,
    StatusReporter,
    SyncDbSaveStrategy,
    _select_strategy,
)


class _FakeRedis:
    def __init__(self, store=None, fail=False):
        self.store = store if store is not None else {}
        self.fail = fail
        self.published = []

    def set(self, key, value, ex=None):
        if self.fail:
            raise RuntimeError("redis down")
        self.store[key] = value

    def publish(self, channel, message):
        self.published.append((channel, message))

    def get(self, key):
        return self.store.get(key)


def _patch_redis(monkeypatch, client):
    import src.backend.redis_util as ru

    monkeypatch.setattr(ru, "get_redis_client", lambda: client)


# --------------------------------------------------------------------------
# save strategies
# --------------------------------------------------------------------------

def test_select_strategy_prefers_redis(monkeypatch):
    _patch_redis(monkeypatch, _FakeRedis())
    assert isinstance(_select_strategy(ProgressState.__new__(ProgressState)), RedisSaveStrategy)


def test_select_strategy_noop_without_repo(monkeypatch):
    _patch_redis(monkeypatch, None)
    state = ProgressState.__new__(ProgressState)
    state.repo = None
    assert isinstance(_select_strategy(state), NoOpSaveStrategy)


def test_select_strategy_sync_db(monkeypatch):
    _patch_redis(monkeypatch, None)
    state = ProgressState.__new__(ProgressState)
    state.repo = MagicMock()
    assert isinstance(_select_strategy(state), SyncDbSaveStrategy)


async def test_select_strategy_async_db(monkeypatch):
    _patch_redis(monkeypatch, None)
    state = ProgressState.__new__(ProgressState)
    state.repo = MagicMock()
    assert isinstance(_select_strategy(state), AsyncDbSaveStrategy)


def test_redis_strategy_requires_client(monkeypatch):
    _patch_redis(monkeypatch, None)
    state = ProgressState.__new__(ProgressState)
    state.task_id = "t1"
    with pytest.raises(RuntimeError, match="Redis client is not available"):
        RedisSaveStrategy().save(state, "{}", "now")


def test_redis_strategy_success_and_failure(monkeypatch):
    client = _FakeRedis()
    _patch_redis(monkeypatch, client)
    state = ProgressState.__new__(ProgressState)
    state.task_id = "t1"
    RedisSaveStrategy().save(state, '{"a": 1}', "now")
    assert "task_status:t1" in client.store
    assert client.published

    _patch_redis(monkeypatch, _FakeRedis(fail=True))
    with pytest.raises(RuntimeError):
        RedisSaveStrategy().save(state, "{}", "now")


def test_sync_db_strategy(monkeypatch):
    state = ProgressState.__new__(ProgressState)
    state.task_id = "t1"
    state.repo = None
    SyncDbSaveStrategy().save(state, "{}", "now")  # no repo -> noop

    state.repo = MagicMock()
    SyncDbSaveStrategy().save(state, "{}", "now")
    state.repo.save_internal_state_sync.assert_called_once()

    state.repo.save_internal_state_sync.side_effect = RuntimeError("db down")
    SyncDbSaveStrategy().save(state, "{}", "now")  # logged, not raised


async def test_async_db_strategy(monkeypatch):
    state = ProgressState.__new__(ProgressState)
    state.task_id = "t1"
    state.repo = None
    AsyncDbSaveStrategy().save(state, "{}", "now")

    async def _save(*a, **k):
        return None

    state.repo = MagicMock()
    state.repo.db.save_internal_state = _save
    AsyncDbSaveStrategy().save(state, "{}", "now")
    await asyncio.sleep(0)

    async def _boom(*a, **k):
        raise RuntimeError("db down")

    state.repo.db.save_internal_state = _boom
    AsyncDbSaveStrategy().save(state, "{}", "now")
    await asyncio.sleep(0)


def test_async_db_strategy_without_loop(monkeypatch):
    state = ProgressState.__new__(ProgressState)
    state.task_id = "t1"
    state.repo = MagicMock()
    with pytest.raises(RuntimeError, match="No running event loop"):
        AsyncDbSaveStrategy().save(state, "{}", "now")


def test_noop_strategy():
    NoOpSaveStrategy().save(MagicMock(), "{}", "now")


# --------------------------------------------------------------------------
# ProgressState
# --------------------------------------------------------------------------

def test_progress_state_defaults(monkeypatch):
    _patch_redis(monkeypatch, None)
    state = ProgressState()
    assert state.task_id.startswith("task_")
    assert state.message == "準備中..."
    assert state.token_usage == {"prompt": 0, "completion": 0, "calls": 0}
    assert isinstance(state._save_strategy, NoOpSaveStrategy)


def test_progress_state_update_and_stop(monkeypatch):
    saved = []
    _patch_redis(monkeypatch, None)
    state = ProgressState(task_id="t1", user_id=7, skip_initial_save=True)
    monkeypatch.setattr(state, "_save_to_db", lambda: saved.append(1))

    state.update("開始", sub_message="初期化")
    assert state.message == "開始"
    assert state.sub_message == "初期化"

    # repeated identical message is not duplicated
    state.update("開始", sub_message="初期化")
    assert len(state.logs) == 1

    state.update("進捗", step=3, total=10, error="boom")
    assert state.current_step == 3
    assert state.total_steps == 10
    assert state.error == "boom"

    state.stop()
    assert state.should_stop() is True
    assert any("停止" in line for line in state.logs)
    assert saved


def test_progress_state_serialization_uses_encoder(monkeypatch):
    _patch_redis(monkeypatch, None)
    state = ProgressState(task_id="t1", skip_initial_save=True)
    state.result_data = {"raw": b"bytes", "obj": object()}
    state._save_strategy = MagicMock()
    state._save_to_db()
    payload = state._save_strategy.save.call_args[0][1]
    decoded = json.loads(payload)
    assert decoded["result_data"]["raw"] == "<bytes>"
    assert isinstance(decoded["result_data"]["obj"], str)
    assert decoded["user_id"] is None


def test_progress_state_save_skipped_without_task_id(monkeypatch):
    _patch_redis(monkeypatch, None)
    state = ProgressState(task_id="t1", skip_initial_save=True)
    state.task_id = ""
    state._save_strategy = MagicMock()
    state._save_to_db()
    state._save_strategy.save.assert_not_called()


def test_should_stop_reads_redis_flag(monkeypatch):
    store = {"task_status:t1": json.dumps({"is_running": False})}
    _patch_redis(monkeypatch, _FakeRedis(store))
    state = ProgressState(task_id="t1", skip_initial_save=True)
    assert state.should_stop() is True


def test_should_stop_ignores_running_flag(monkeypatch):
    store = {"task_status:t1": json.dumps({"is_running": True})}
    _patch_redis(monkeypatch, _FakeRedis(store))
    state = ProgressState(task_id="t1", skip_initial_save=True)
    assert state.should_stop() is False


def test_should_stop_handles_redis_error(monkeypatch):
    class _Broken:
        def get(self, key):
            raise RuntimeError("redis down")

    _patch_redis(monkeypatch, _Broken())
    state = ProgressState(task_id="t1", skip_initial_save=True)
    assert state.should_stop() is False


def test_should_stop_rate_limits_checks(monkeypatch):
    client = _FakeRedis({"task_status:t1": json.dumps({"is_running": True})})
    _patch_redis(monkeypatch, client)
    state = ProgressState(task_id="t1", skip_initial_save=True)
    assert state.should_stop() is False
    state._last_stop_check = state._last_stop_check + 100  # force a fresh check
    assert state.should_stop() is False


# --------------------------------------------------------------------------
# Reporters
# --------------------------------------------------------------------------

def test_background_report(monkeypatch):
    _patch_redis(monkeypatch, None)
    state = ProgressState(task_id="t1", skip_initial_save=True)
    reporter = BackgroundReporter(state)
    reporter.logger = MagicMock()

    reporter.report("info message")
    assert state.message == "ℹ️ info message"
    reporter.report("warn", level="warning")
    assert state.message == "⚠️ warn"
    reporter.report("bad", level="error")
    assert state.error == "bad"

    state.stop()
    reporter.report("ignored")
    assert state.message == "🚨 bad"


def test_background_report_progress_and_streaming(monkeypatch):
    _patch_redis(monkeypatch, None)
    state = ProgressState(task_id="t1", skip_initial_save=True)
    reporter = BackgroundReporter(state)
    reporter.logger = MagicMock()

    reporter.update_progress(2, 5, "本文", sub_text="3000字")
    assert state.current_step == 2
    assert state.total_steps == 5

    reporter.update_streaming_text(" streamed ")
    assert state.streaming_text == " streamed "

    state.stop()
    reporter.update_progress(1, 1, "x")
    reporter.update_streaming_text("y")
    assert state.streaming_text == " streamed "


def test_background_report_exception(monkeypatch):
    _patch_redis(monkeypatch, None)
    state = ProgressState(task_id="t1", skip_initial_save=True)
    reporter = BackgroundReporter(state)
    reporter.logger = MagicMock()

    reporter.report_exception(ValueError("boom"), context="writing")
    assert "writing - ValueError: boom" in state.error
    reporter.report_exception(KeyError("missing"))
    assert "KeyError" in state.error


def test_status_reporter(monkeypatch):
    _patch_redis(monkeypatch, None)
    state = ProgressState(task_id="t1", skip_initial_save=True)
    r = StatusReporter(state)
    r.report("hello")
    r.report("bad", level="error")
    r.update_progress(1, 3, "step", sub_text="sub")
    assert state.current_step == 1
    r.update_streaming_text("text")
    assert state.streaming_text == "text"

    empty = StatusReporter()
    empty.update_progress(1, 1, "x")
    empty.update_streaming_text("y")


def test_module_level_report_exception_helper(monkeypatch, caplog):
    """モジュールレベル関数 `report_exception` のメッセージ整形を検証する。

    `report_exception` はクラス外（モジュールレベル）で定義された関数で、
    第1引数にレポーターを受け取り `self.report(msg, level="error")` を呼ぶ
    （src/backend/background.py:306-313）。モジュールグローバル `self` を読むOLA
    ではないため、`bg.__dict__["self"]` への setitem は不要。

    また基本 `StatusReporter.report` は仕様どおりログへ出力し
    `state.error` へは書かない（src/backend/background.py:289-293、
    「最小実装を提供しサブクラスで上書きする前提」の基底クラス）。
    `state.error` への永続化は `BackgroundReporter` の責務である。
    したがってここでは、整形されたメッセージが `report()` に
    正しい level と共に渡ることを確認する。
    """
    _patch_redis(monkeypatch, None)

    class SpyReporter:
        def __init__(self):
            self.calls = []

        def report(self, message, level="info"):
            self.calls.append((message, level))

    reporter = SpyReporter()

    with caplog.at_level("INFO"):
        bg.report_exception(reporter, ValueError("oops"), context="ctx")
        bg.report_exception(reporter, ValueError("oops"))

    assert reporter.calls[0] == ("ctx - ValueError: oops", "error")
    assert reporter.calls[1] == ("ValueError: oops", "error")


# --------------------------------------------------------------------------
# BackgroundTaskManager
# --------------------------------------------------------------------------

def test_background_task_manager_lifecycle(monkeypatch):
    _patch_redis(monkeypatch, None)
    mgr = BackgroundTaskManager()
    task_id = mgr.create_task("generate")
    assert task_id in mgr.list_tasks()

    status = mgr.get_status(task_id)
    assert status["is_running"] is True
    assert "generate" in status["message"]
    assert status["token_usage"] == {"prompt": 0, "completion": 0, "calls": 0}

    mgr.update_progress(task_id, 50, "halfway")
    assert mgr.get_status(task_id)["progress"] == 50
    mgr.update_progress("unknown", 1, "x")

    assert mgr.stop_task(task_id) is True
    assert mgr.get_status(task_id) is not None
    assert mgr.stop_task("unknown") is False
    assert mgr.get_status("unknown") is None

    assert mgr.delete_task(task_id) is True
    assert mgr.delete_task(task_id) is False
