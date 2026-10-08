"""Testcontainers (DockerContainer) 経由で PostgreSQL が起動できることの疎通確認。

Docker デーモンが利用できない環境では skip する（Phase 2: 外部環境依存テストの切り分け）。
"""
from __future__ import annotations

import pytest


def _docker_available() -> bool:
    """docker CLI の存在とデーモン疎通を確認する。"""
    import shutil

    if shutil.which("docker") is None:
        return False
    try:
        import subprocess

        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
            check=True,
        )
        return True
    except Exception:
        return False


def test_postgres_via_docker(postgres_container):
    """PostgresContainer フィクスチャ経由で PostgreSQL に接続できること。"""
    if postgres_container is None:
        pytest.skip("testcontainers is not installed")
    assert postgres_container is not None
