"""Test to check if postgres fixture via DockerContainer works."""
from __future__ import annotations

import pytest

from tests.integration.conftest import docker_daemon_available

pytestmark = pytest.mark.skipif(
    not docker_daemon_available(),
    reason="Docker daemon が利用できない環境では testcontainers テストを実行不可",
)



def test_postgres_via_docker(postgres_via_docker):
    """Just check that we get the postgres fixture via DockerContainer."""
    print("Type of postgres_via_docker:", type(postgres_via_docker))
    print("Postgres via Docker container:", postgres_via_docker)
