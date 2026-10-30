"""Server entrypoint contract test (TRACK-A9).

src.backend.server:app が引き続き FastAPI インスタンスを提供し、
uvicorn 起動経路が従来どおり動作することを保証する。
"""

from __future__ import annotations

from fastapi import FastAPI

from src.backend.server import app


def test_server_app_is_fastapi_instance():
    """src.backend.server:app が FastAPI インスタンスであること."""
    assert isinstance(app, FastAPI)


def test_server_app_has_routes():
    """app にルーターが登録されていること（空ではない）."""
    assert len(app.routes) > 0


def test_server_app_has_lifespan():
    """app に lifespan ハンドラが登録されていること."""
    assert app.router.lifespan_context is not None
