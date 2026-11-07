"""Test to check if redis fixture works."""
from __future__ import annotations

import pytest

from tests.integration.conftest import docker_daemon_available

pytestmark = pytest.mark.skipif(
    not docker_daemon_available(),
    reason="Docker daemon が利用できない環境では testcontainers テストを実行不可",
)



def test_redis_fixture(redis_container):
    """Just check that we get the redis fixture."""
    print("Type of redis_container:", type(redis_container))
    print("Redis container:", redis_container)
