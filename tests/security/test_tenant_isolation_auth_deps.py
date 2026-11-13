"""Step 18 (テナント分離): グローバル状態ルーターの認証＋user_id スコープ化。

- agent_memory.py: ルータレベル + 各エンドポイントに current_user 依存、メモリマネージャに user_id をスコープ
- dashboard.py: 同上、FusionEngine に user_id をスコープ
- conflicts.py: 同上、ConflictStore に user_id をスコープ
- subtext.py: ルータレベル認証（全エンドポイントが認証必須に）
"""
from __future__ import annotations

import inspect

from src.backend.routers import agent_memory, dashboard, conflicts, subtext


def test_agent_memory_has_auth_deps():
    """agent_memory ルータに認証依存がある（Step 18）。"""
    src = inspect.getsource(agent_memory)
    assert "get_current_user" in src
    assert "dependencies=[Depends(get_current_user)]" in src
    assert "current_user.id" in src


def test_dashboard_has_auth_deps():
    """dashboard ルータに認証依存がある（Step 18）。"""
    src = inspect.getsource(dashboard)
    assert "get_current_user" in src
    assert "dependencies=[Depends(get_current_user)]" in src
    assert "current_user.id" in src


def test_conflicts_has_auth_deps():
    """conflicts ルータに認証依存がある（Step 18）。"""
    src = inspect.getsource(conflicts)
    assert "get_current_user" in src
    assert "dependencies=[Depends(get_current_user)]" in src
    assert "current_user.id" in src


def test_subtext_has_auth_deps():
    """subtext ルータに認証依存がある（Step 18）。"""
    src = inspect.getsource(subtext)
    assert "get_current_user" in src
    assert "dependencies=[Depends(get_current_user)]" in src
