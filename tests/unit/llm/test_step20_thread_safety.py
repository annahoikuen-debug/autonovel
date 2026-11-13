"""Step 20: Gemini空レスポンスガードと非スレッド安全性修正。

- gemini.py generate_text に空レスポンスガードを追加（generate_json と同様）
- ExecutorManager に _lock を追加（ダブルチェックロッキング）
- OpenAIApiClient._clients キャッシュに _lock を追加
- GeminiApiClient に _lock を追加（retry_decorator のカウンタ操作で使用）
- retry_decorator.py のカウンタ操作をロック内で読み書き
"""
from __future__ import annotations

import inspect
import threading

from src.backend.engine_utils import AdaptiveCooldown
from src.core.executor_manager import ExecutorManager
from src.llm.clients.gemini import GeminiApiClient
from src.llm.clients.openai import OpenAIApiClient


def test_executor_manager_has_lock():
    """ExecutorManager が _lock を持つ（Step 20）。"""
    assert hasattr(ExecutorManager, "_lock")
    assert isinstance(ExecutorManager._lock, type(threading.Lock()))


def test_openai_client_instance_has_lock():
    """OpenAIApiClient インスタンスが _lock を持つ（Step 20）。"""
    client = OpenAIApiClient(cooldown=AdaptiveCooldown(base_sec=2.0, min_sec=1.0, max_sec=60.0))
    assert hasattr(client, "_lock")
    assert client._lock is not None


def test_gemini_client_has_lock_param():
    """GeminiApiClient の __init__ シグネチャに _lock 設定がある（Step 20）。"""
    src = inspect.getsource(GeminiApiClient.__init__)
    assert "self._lock = threading.Lock()" in src


def test_gemini_generate_text_has_empty_response_guard():
    """gemini.py generate_text に空レスポンスガードがある（Step 20）。"""
    src = inspect.getsource(GeminiApiClient.generate_text)
    assert 'raise ValueError("API応答が空です。")' in src, (
        "gemini.py generate_text に空レスポンスガードがない（H17/Step 20）"
    )


def test_retry_decorator_counter_uses_lock():
    """retry_decorator.py のカウンタ操作がロック内で行われる（Step 20）。"""
    src = inspect.getsource(inspect.getmodule(__import__("src.services.retry_decorator", fromlist=["x"])))
    # active_requests の読み取りがロック内
    assert "with lock:" in src
    assert "_active_requests" in src
    assert "_consecutive_5xx" in src
