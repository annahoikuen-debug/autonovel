"""lifespan の shutdown でプリフェッチタスクが消されることの回帰テスト（PLAN_W6 Step 7）。

F3 DI リファクタ後は lifespan が ``AppWiring`` から依存を受けるため、
モック wiring で構築して検証する。実 wiring の供給リンク（semantic_cache /
huey / init_db）は linkage テストで固定する。
"""

from __future__ import annotations

import inspect
import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))


def _build_lifespan(wiring):
    """実行時に ``build_lifespan`` を import し直して返す。

    ``tests/unit/api/test_plugin_conditional_routing.py`` が
    ``src.interfaces.api.app_factory`` を ``sys.modules`` から消して再 import
    するため、コレクション時キャッシュの関数を使うと
    ``patch("src.interfaces.api.app_factory.configure_logging")`` の対象モジュールと
    ``build_lifespan`` の ``__globals__`` がずれて patch が効かない。
    """
    from src.interfaces.api.app_factory import build_lifespan

    return build_lifespan(wiring)


def _make_wiring(**overrides):
    """テスト用の最小 wiring（依存はすべてモック）。"""
    from src.interfaces.api.app_factory import AppWiring

    base: dict = {
        "routers": (),
        "init_db": MagicMock(),
        "register_error_handlers": MagicMock(),
        "auth_middleware": MagicMock(),
        "build_health_payload": AsyncMock(return_value={"status": "ok"}),
        "health_metrics": MagicMock(),
        "huey_check": None,
        "cancel_prefetch": AsyncMock(return_value=2),
    }
    base.update(overrides)
    return AppWiring(**base)


@pytest.mark.asyncio
async def test_shutdown_cancels_prefetch():
    cancel = AsyncMock(return_value=2)
    init_db = MagicMock()
    wiring = _make_wiring(cancel_prefetch=cancel, init_db=init_db)
    lifespan = _build_lifespan(wiring)
    with (
        patch("src.core.executor_manager.executor_manager") as ex,
        patch("src.interfaces.api.app_factory.configure_logging") as configure,
    ):
        async with lifespan(MagicMock()):
            pass
    cancel.assert_awaited_once()
    ex.shutdown.assert_called_once()
    init_db.assert_called_once()
    configure.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_runs_even_if_startup_side_effect_fails():
    cancel = AsyncMock(return_value=0)
    wiring = _make_wiring(cancel_prefetch=cancel)
    lifespan = _build_lifespan(wiring)
    with (
        patch("src.core.executor_manager.executor_manager"),
        patch("src.interfaces.api.app_factory.configure_logging"),
    ):
        with pytest.raises(RuntimeError):
            async with lifespan(MagicMock()):
                raise RuntimeError("テスト用")
    # 例外は finally を通るため m は await 済みになる
    assert cancel.await_count == 1


@pytest.mark.asyncio
async def test_shutdown_survives_prefetch_cancel_failure():
    """プリフェッチ取り消しが失敗しても executor_manager の shutdown は必ず走る。"""
    cancel = AsyncMock(side_effect=RuntimeError("boom"))
    wiring = _make_wiring(cancel_prefetch=cancel)
    lifespan = _build_lifespan(wiring)
    with (
        patch("src.core.executor_manager.executor_manager") as ex,
        patch("src.interfaces.api.app_factory.configure_logging"),
    ):
        async with lifespan(MagicMock()):
            pass
    ex.shutdown.assert_called_once()


def test_lifespan_is_asynccontextmanager():
    lifespan = _build_lifespan(_make_wiring())
    assert hasattr(lifespan, "__wrapped__") or inspect.isasyncgenfunction(lifespan)


@pytest.mark.asyncio
async def test_lifespan_completes_with_optional_side_effects_unwired():
    """huey_check / cancel_prefetch が None でも lifespan が完走すること。"""
    wiring = _make_wiring(huey_check=None, cancel_prefetch=None)
    lifespan = _build_lifespan(wiring)
    with (
        patch("src.core.executor_manager.executor_manager") as ex,
        patch("src.interfaces.api.app_factory.configure_logging"),
    ):
        async with lifespan(MagicMock()):
            pass
    ex.shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_real_wiring_supplies_prefetch_cancellation():
    """実 wiring の cancel_prefetch が src.services.semantic_cache を指すこと。"""
    from src.backend.wiring import build_wiring

    wiring = build_wiring()
    assert wiring.cancel_prefetch is not None
    with patch(
        "src.services.semantic_cache.cancel_all_prefetch",
        new=AsyncMock(return_value=7),
    ) as m:
        cancelled = await wiring.cancel_prefetch()
    assert cancelled == 7
    m.assert_awaited_once()


def test_real_wiring_supplies_huey_check():
    """実 wiring の huey_check が src.backend.tasks.huey を指すこと。"""
    from src.backend.wiring import build_wiring

    wiring = build_wiring()
    assert wiring.huey_check is not None
    with patch(
        "src.backend.tasks.huey.check_huey_health",
        new=MagicMock(return_value={"ok": True}),
    ) as m:
        result = wiring.huey_check()
    assert result == {"ok": True}
    m.assert_called_once()


def test_real_wiring_supplies_init_db():
    """実 wiring の init_db が src.backend.database.init_db であること。"""
    from src.backend.database import init_db
    from src.backend.wiring import build_wiring

    assert build_wiring().init_db is init_db
