"""``src/services/resilience.py`` の**実挙動**を検証する。

H1 M1 でこのモジュールの ``check_database`` を書き換えた际、
「import できる」「関数が存在する」だけでは無意味であることに気づいた。
実際に素の同期コンテキストから呼んで ``ok`` が返ることを検証する。

前回の実装は 2 代続けて壊れていた:
1. 旧: ``asyncio.get_event_loop().run_until_complete()`` — Python 3.14 では
   ``There is no current event loop`` で常に "error"
2. 途中案: ``AsyncEngine.sync_engine.connect()`` — greenlet ブリッジ前提のため
   ``greenlet_spawn has not been called`` で常に "error"

どちらも「mock を 넣으면緑」で素の呼び出し paths는 緑にならないため、
このテストは **mock を使わない**。
"""
from __future__ import annotations

from src.services.resilience import _sync_engine_url, check_database, get_system_status


def test_check_database_returns_ok_in_plain_sync_context():
    """イベントループの無い素のコンテキストで、実 DB に SELECT 1 が通ること。"""
    assert check_database() == "ok"


def test_check_database_does_not_create_an_event_loop():
    """``check_database`` 呼び出しでイベントループを生成しないこと。

    ``asyncio.get_event_loop`` を使う実装は Python 3.14 で
    RuntimeError になるが、その例外を握りつぶして "error" を返すだけでは
    検出できないため、生成されたループの有無を直接見る。
    """
    import asyncio.events

    policy = asyncio.events.get_event_loop_policy()
    before = getattr(policy, "_local", None)
    loop_before = getattr(before, "loop", None) if before is not None else None

    assert check_database() == "ok"

    policy = asyncio.events.get_event_loop_policy()
    after = getattr(policy, "_local", None)
    loop_after = getattr(after, "loop", None) if after is not None else None
    assert loop_after is loop_before, (
        f"check_database がイベントループを生成した: {loop_before!r} -> {loop_after!r}"
    )


def test_get_system_status_reports_database_ok():
    """``get_system_status()`` の database フィールドが "ok" であること。

    ここが 2 世代にわたって "error" を返し続けた（= 恒久的に嘘をついていた）。
    """
    status = get_system_status()
    assert status["database"] == "ok", status


def test_sync_engine_url_drops_the_async_driver():
    from sqlalchemy.engine import make_url

    assert _sync_engine_url(
        make_url("sqlite+aiosqlite:///./x.db")
    ).get_backend_name() == "sqlite"
    assert _sync_engine_url(
        make_url("postgresql+asyncpg://u:p@h/db")
    ).get_backend_name() == "postgresql"


def test_check_database_returns_error_instead_of_raising_when_db_is_broken(monkeypatch):
    """DB が壊れていても例外を投げずに "error" を返すこと（元の契約）。"""
    import src.core.container as container_mod

    class _BrokenManager:
        class engine:  # noqa: N801
            url = "not-a-url"

    monkeypatch.setattr(
        container_mod.AppContainer, "db", staticmethod(lambda: _BrokenManager())
    )
    assert check_database() == "error"
