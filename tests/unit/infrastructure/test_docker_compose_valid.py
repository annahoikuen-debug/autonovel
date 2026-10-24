"""Step 14 検証テスト: Docker 構成検証テスト.

Compose 設定が常に妥当な構文を保っていることを検証する。
`docker compose config` コマンドが終了コード 0 を返すことをテストする。
Docker が利用できない環境では YAML パースによる構文検査にフォールバックする。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILES = [
    PROJECT_ROOT / "docker-compose.yml",
    PROJECT_ROOT / "docker-compose.prod.yml",
]

# `docker compose config` は `${VAR:?...}` の必須変数が未設定だと構文検証前に
# エラーで落ちる。検証したいのは YAML 構文と compose の整合性なので、
# 必須変数に検証専用のダミー値を注入する（本物のシークレットは使わない）。
_DUMMY_COMPOSE_ENV = {
    "POSTGRES_PASSWORD": "compose-syntax-check-only",
    "REDIS_PASSWORD": "compose-syntax-check-only",
    "LLM_PROVIDER": "mock",
    "ALLOWED_API_KEYS": "compose-syntax-check-only-key",
    "CORS_ORIGINS": "http://localhost:5173",
    "JWT_SECRET_KEY": "compose-syntax-check-only-jwt-secret-32bytes",
}


def _compose_env():
    import os

    return {**os.environ, **_DUMMY_COMPOSE_ENV}


def _docker_available() -> bool:
    return shutil.which("docker") is not None


class TestComposeConfigCommand:
    """docker compose config が終了コード 0 を返すこと。"""

    @pytest.mark.skipif(not _docker_available(), reason="docker CLI not available")
    def test_dev_compose_config_valid(self):
        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.yml", "config", "--quiet"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            env=_compose_env(),
        )
        assert result.returncode == 0, (
            f"docker compose config failed (rc={result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    @pytest.mark.skipif(not _docker_available(), reason="docker CLI not available")
    def test_prod_compose_config_valid(self):
        """prod compose は必須変数 (POSTGRES_PASSWORD / JWT_SECRET_KEY 等) を要求するため
        構文検証用のダミー値を注入して `docker compose config` を実行する。"""
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                "docker-compose.prod.yml",
                "config",
                "--quiet",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            env=_compose_env(),
        )
        assert result.returncode == 0, (
            f"docker compose config (prod) failed (rc={result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


class TestComposeFileStructure:
    """Docker CLI が無い環境向けの YAML 構文検査。"""

    @pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.name)
    def test_compose_file_exists(self, compose_file: Path):
        assert compose_file.exists(), f"missing: {compose_file}"

    def test_dev_compose_yaml_parses(self):
        """YAML としてパースでき、services を持つこと。"""
        yaml = pytest.importorskip("yaml")
        content = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        assert isinstance(data, dict)
        assert "services" in data
        assert "backend" in data["services"]

    def test_dev_compose_backend_has_resource_limits(self):
        """Step 10: backend にメモリ制限が設定されていること。"""
        yaml = pytest.importorskip("yaml")
        content = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        backend = data["services"]["backend"]
        limits = backend.get("deploy", {}).get("resources", {}).get("limits", {})
        assert limits.get("memory") == "1024M"

    def test_dev_compose_backend_health_gated_dependencies(self):
        """Step 12: depends_on に condition: service_healthy が適用されていること。"""
        yaml = pytest.importorskip("yaml")
        content = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        backend = data["services"]["backend"]
        deps = backend.get("depends_on", {})
        for service in ("db", "redis"):
            assert service in deps, f"backend must depend on {service}"
            assert deps[service].get("condition") == "service_healthy"

    def test_prod_compose_yaml_parses(self):
        yaml = pytest.importorskip("yaml")
        content = (PROJECT_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        assert isinstance(data, dict)
        assert "services" in data

    def test_dockerfile_multistage_optimized(self):
        """Step 11: Dockerfile がマルチステージビルド（builder/runner）であること。"""
        content = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "AS builder" in content
        assert "AS runner" in content
        assert "COPY --from=builder" in content
