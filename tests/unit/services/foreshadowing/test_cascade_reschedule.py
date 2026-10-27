"""連鎖延期（cascade reschedule）の回帰テスト（PLAN_W5 Step 7）。"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from src.services.foreshadowing.rescheduler import ForeshadowingRescheduler  # noqa: E402

ROWS = [
    {"id": 1, "target_episode": 5, "status": "planted", "description": "魔導書を得る"},
    {"id": 2, "target_episode": 9, "status": "planted", "description": "後続の結果に解読に失敗する"},
    {"id": 3, "target_episode": 20, "status": "planted", "description": "後続の結果に真相が判明する"},
]


def _repo(ok: bool = True):
    repo = MagicMock()
    repo.update_target_episode = AsyncMock(return_value=ok)
    return repo


@pytest.mark.asyncio
async def test_disabled_flag_is_noop(monkeypatch):
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "0")
    repo = _repo()
    out = await ForeshadowingRescheduler.cascade_reschedule(ROWS, 1, 5, repo, max_episode=40)
    assert out == []
    assert repo.update_target_episode.await_count == 0


@pytest.mark.asyncio
async def test_enabled_moves_dependents(monkeypatch):
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "1")
    repo = _repo()
    out = await ForeshadowingRescheduler.cascade_reschedule(ROWS, 1, 5, repo, max_episode=40)
    assert repo.update_target_episode.await_count == 2
    assert [i for i, _ in out] == [2, 3]


@pytest.mark.asyncio
async def test_cas_rejection_is_swallowed(monkeypatch):
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "1")
    repo = _repo(ok=False)
    out = await ForeshadowingRescheduler.cascade_reschedule(ROWS, 1, 5, repo, max_episode=40)
    assert out == []
    assert repo.update_target_episode.await_count == 2


@pytest.mark.asyncio
async def test_missing_repo_method_is_safe(monkeypatch):
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "1")
    repo = MagicMock(spec=[])  # update_target_episode を持たない
    out = await ForeshadowingRescheduler.cascade_reschedule(ROWS, 1, 5, repo, max_episode=40)
    assert out == []


@pytest.mark.asyncio
async def test_no_dependents_is_noop(monkeypatch):
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "1")
    repo = _repo()
    out = await ForeshadowingRescheduler.cascade_reschedule(ROWS, 3, 20, repo, max_episode=40)
    assert out == []
    assert repo.update_target_episode.await_count == 0


@pytest.mark.asyncio
async def test_unawaitable_repo_attribute_is_swallowed(monkeypatch):
    """`MagicMock()`（await 不能）を渡しても例外を漏らさない。"""
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "1")
    out = await ForeshadowingRescheduler.cascade_reschedule(
        ROWS, 1, 5, MagicMock(), max_episode=40
    )
    assert out == []


@pytest.mark.asyncio
async def test_cascade_is_capped(monkeypatch):
    """`MAX_CASCADE` を超える依存を処理しない。"""
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "1")
    rows = [
        {"id": 1, "status": "planted", "description": "起"},
        *[
            {"id": i, "status": "planted", "description": "後続の結果"}
            for i in range(2, 2 + ForeshadowingRescheduler.MAX_CASCADE + 5)
        ],
    ]
    repo = _repo()
    out = await ForeshadowingRescheduler.cascade_reschedule(rows, 1, 5, repo, max_episode=40)
    assert len(out) == ForeshadowingRescheduler.MAX_CASCADE


@pytest.mark.asyncio
async def test_existing_reschedule_is_untouched(monkeypatch):
    """既存 `reschedule_foreshadowing` は従来どおり 1 本だけ延期する。"""
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "0")
    repo = _repo()
    new_target = await ForeshadowingRescheduler.reschedule_foreshadowing(1, 5, repo, max_episode=40)
    assert new_target is not None
    assert repo.update_target_episode.await_args.args == (1, new_target)
