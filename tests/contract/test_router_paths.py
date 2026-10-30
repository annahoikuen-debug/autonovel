"""Router path contract test (TRACK-A8).

Old import paths (src.backend.routers.*) must continue to provide the same
OpenAPI paths after routers were moved to src.interfaces.api.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from src.backend.routers.metrics import router as metrics_router
from src.backend.routers.platform_export import router as platform_export_router
from src.backend.routers.styles import router as styles_router


def _collect_paths(router) -> set[str]:
    paths: set[str] = set()
    for route in router.routes:
        if isinstance(route, APIRoute):
            paths.add(route.path)
    return paths


def test_metrics_router_paths():
    """metrics ルーターが /metrics と /metrics/huey-sqlite-busy を提供すること."""
    paths = _collect_paths(metrics_router)
    assert "/metrics" in paths
    assert "/metrics/huey-sqlite-busy" in paths


def test_platform_export_router_paths():
    """platform_export ルーターが /api/export/copy/ を提供すること."""
    paths = _collect_paths(platform_export_router)
    assert "/api/export/copy/" in paths


def test_styles_router_paths():
    """styles ルーターが /api/styles/* を提供すること."""
    paths = _collect_paths(styles_router)
    assert "/api/styles/all" in paths
    assert "/api/styles/categories" in paths
    assert "/api/styles/presets" in paths
    assert "/api/styles/distill" in paths
    assert "/api/styles/reformat" in paths
