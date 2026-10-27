"""lifespan の shutdown でプリフェッチタスクが消されることの回帰テスト（PLAN_W6 Step 7）。"""

from __future__ import annotations

import inspect
import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from src.backend.server import lifespan  # noqa: E402


@pytest.mark.asyncio
async def test_shutdown_cancels_prefetch():
    with (
        patch(
            "src.services.semantic_cache.cancel_all_prefetch", new=AsyncMock(return_value=2)
        ) as m,
        patch("src.core.executor_manager.executor_manager") as ex,
        patch("src.backend.server.init_db"),
        patch("src.backend.server.configure_logging"),
    ):
        async with lifespan(MagicMock()):
            pass
    m.assert_awaited_once()
    ex.shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_runs_even_if_startup_side_effect_fails():
    with (
        patch(
            "src.services.semantic_cache.cancel_all_prefetch", new=AsyncMock(return_value=0)
        ) as m,
        patch("src.core.executor_manager.executor_manager"),
        patch("src.backend.server.init_db"),
        patch("src.backend.server.configure_logging"),
    ):
        with pytest.raises(RuntimeError):
            async with lifespan(MagicMock()):
                raise RuntimeError("テスト用")
    # 例外は finally を通るため m は await 済みになる
    assert m.await_count == 1


@pytest.mark.asyncio
async def test_shutdown_survives_prefetch_cancel_failure():
    """プリフェッチ取り消しが失敗しても executor_manager の shutdown は必ず走る。"""
    with (
        patch(
            "src.services.semantic_cache.cancel_all_prefetch",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("src.core.executor_manager.executor_manager") as ex,
        patch("src.backend.server.init_db"),
        patch("src.backend.server.configure_logging"),
    ):
        async with lifespan(MagicMock()):
                pass
        ex.shutdown.assert_called_once()


def test_lifespan_is_asynccontextmanager():
    assert hasattr(lifespan, "__wrapped__") or inspect.isasyncgenfunction(lifespan)
