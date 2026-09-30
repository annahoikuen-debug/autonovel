"""CAS 拒否理由が `last_rejection` に残ることの回帰テスト（PLAN_W5 Step 8）。"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from src.infrastructure.repositories.foreshadowing_repo import (  # noqa: E402
    DbForeshadowingRepository,
)
from tests.unit.database.test_foreshadowing_repo import (  # noqa: E402
    _plant,
    create_test_db,
)

_ALLOWED_KEYS = {"id", "target_status", "reason", "op"}


@pytest.mark.asyncio
async def test_illegal_transition_records_reason():
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            fid = await _plant(session_factory)
            assert await repo.resolve(fid, 9) is True
            assert await repo.resolve(fid, 10) is False  # resolved は終端
            assert repo.last_rejection["reason"] in {"illegal_transition", "not_found"}
            assert repo.last_rejection["id"] == fid
            assert repo.last_rejection["op"] == "transition"


@pytest.mark.asyncio
async def test_not_found_records_reason():
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.resolve(999999, 3) is False
            assert repo.last_rejection["reason"] == "not_found"
            assert repo.last_rejection["op"] == "transition"


@pytest.mark.asyncio
async def test_before_plant_episode_records_reason():
    """`_plant` の既定は `planted_episode=3`。第2話での回収は拒否される。"""
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            fid = await _plant(session_factory)
            assert await repo.resolve(fid, 2) is False
            assert repo.last_rejection["reason"] == "before_plant_episode"


@pytest.mark.asyncio
async def test_op_field_is_set_for_update_target():
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.update_target_episode(999999, 8) is False
            assert repo.last_rejection["op"] == "update_target"
            assert repo.last_rejection["reason"] == "not_found"


@pytest.mark.asyncio
async def test_horizon_zero_records_reason_for_update_target():
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            fid = await _plant(session_factory)  # planted=3
            assert await repo.update_target_episode(fid, 3) is False
            assert repo.last_rejection["reason"] == "horizon_zero"
            assert repo.last_rejection["op"] == "update_target"


@pytest.mark.asyncio
async def test_success_does_not_crash_and_keys_are_bounded():
    async with create_test_db() as session_factory:
        async with session_factory() as session:
            repo = DbForeshadowingRepository(session)
            fid = await _plant(session_factory)
            assert await repo.resolve(fid, 9) is True
            assert set(repo.last_rejection) <= _ALLOWED_KEYS
