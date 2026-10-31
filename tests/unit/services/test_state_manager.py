"""StateManager の単体テスト。"""

from __future__ import annotations

import pytest

from src.services.state_manager import StateManager


class _FakeMisc:
    """uow.misc の代替。"""

    def __init__(self):
        self._store: dict[str, object] = {}

    async def save_internal_state(self, key: str, value: object) -> None:
        self._store[key] = value

    async def get_internal_state(self, key: str) -> object | None:
        return self._store.get(key)


class _FakeUoW:
    """UnitOfWork の代替。async with で利用可能。"""

    def __init__(self):
        self.misc = _FakeMisc()
        self.committed = False
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.closed = True
        return False

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_save_and_get_state_roundtrip():
    """save_state で保存した値を get_state で取得できること。"""
    uow = _FakeUoW()
    mgr = StateManager(uow)

    await mgr.save_state("user:1:theme", "dark")
    assert uow.committed is True

    value = await mgr.get_state("user:1:theme")
    assert value == "dark"


@pytest.mark.asyncio
async def test_get_state_missing_key_returns_none():
    """存在しないキーを取得すると None を返すこと。"""
    uow = _FakeUoW()
    mgr = StateManager(uow)

    value = await mgr.get_state("nonexistent:key")
    assert value is None


@pytest.mark.asyncio
async def test_save_state_overwrites_existing_value():
    """同じキーを保存すると値が上書きされること。"""
    uow = _FakeUoW()
    mgr = StateManager(uow)

    await mgr.save_state("counter", 1)
    await mgr.save_state("counter", 2)

    value = await mgr.get_state("counter")
    assert value == 2
    assert uow.committed is True
