"""``verify_branch_belongs_to_book`` は episodes.py 側でも共有されていることの確認。"""
from __future__ import annotations

import inspect

from src.backend.routers import episodes
from src.backend.security import branch_guard


def test_episodes_delegates_to_branch_guard():
    """episodes.py が旧実装ではなく共有モジュールを参照していること。"""
    src = inspect.getsource(episodes)
    assert "from src.backend.security.branch_guard import" in src, (
        "episodes.py が branch_guard を import していない。"
        "ロジックが二重に存在している。"
    )


def test_branch_guard_exports_the_verifier():
    assert hasattr(branch_guard, "verify_branch_belongs_to_book")
