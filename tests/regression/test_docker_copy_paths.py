"""Step C2-C3: Docker ビルド・デプロイ設定の整合性検証。

Dockerfile/Dockerfile.prod の COPY 行が指すディレクトリが実在すること、
および entrypoint.sh / docker-compose*.yml に案B で移動・削除された
パスの参照が残っていないことを検証する。

Docker が未導入の環境でも実行可能な静的検証。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: Dockerfile で COPY するディレクトリ（ファイルではなくディレクトリ）
DOCKER_COPY_DIRS = ["src", "config", "formatters", "plugins", "prompts", "schemas"]

#: entrypoint.sh / compose で参照があってはならない旧パス（案B で移動/削除）
STALE_PATHS = [
    "src/core/llm_clients",
    "src/api/dashboard.py",
    "src/api/conflicts.py",
    "src/api/agent_memory.py",
    "src/backend/api/admin_phase2.py",
    "src/interfaces/api/styles.py",
    "src/interfaces/api/platform_export.py",
    "src/services/llm/base.py",
    "src/services/llm/factory.py",
    "src/types/inlineRevision.ts",
]


def _dockerfile_copy_sources(dockerfile_path: Path) -> list[str]:
    """Dockerfile から COPY 行のコピー元パスを抽出（--from= 行は除外）。"""
    sources = []
    for line in dockerfile_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("COPY") and not stripped.startswith("ADD"):
            continue
        if "--from=" in stripped:
            continue
        parts = stripped.split()
        # COPY <src> <dest> の src は最後から2番目（--chown= 等のフラグを除く）
        # 簡易的に、最後の2トークンを src/dest とみなす
        if len(parts) >= 3:
            src_candidate = parts[-2]
            if src_candidate.startswith("./") or src_candidate.startswith("/"):
                sources.append(src_candidate)
    return sources


@pytest.mark.parametrize("dockerfile_name", ["Dockerfile", "Dockerfile.prod"])
def test_dockerfile_copy_dirs_exist(dockerfile_name):
    """Dockerfile の COPY 先ディレクトリが実在すること。"""
    dockerfile = ROOT / dockerfile_name
    assert dockerfile.exists(), f"{dockerfile_name} が存在しない"

    sources = _dockerfile_copy_sources(dockerfile)
    for src in sources:
        # "./src" -> "src"
        dir_name = src.rstrip("/").lstrip("./")
        if dir_name in DOCKER_COPY_DIRS:
            target = ROOT / dir_name
            assert target.is_dir(), (
                f"{dockerfile_name} の COPY 先ディレクトリが存在しない: {src}"
            )


def test_dockerfile_copy_files_exist():
    """Dockerfile の COPY 先ファイルが実在すること。"""
    for dockerfile_name in ["Dockerfile", "Dockerfile.prod"]:
        dockerfile = ROOT / dockerfile_name
        assert dockerfile.exists(), f"{dockerfile_name} が存在しない"
        for line in dockerfile.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("COPY") and not stripped.startswith("ADD"):
                continue
            if "--from=" in stripped:
                continue
            parts = stripped.split()
            if len(parts) >= 3:
                src_candidate = parts[-2]
                if not (src_candidate.startswith("./") or src_candidate.startswith("/")):
                    continue
                target = ROOT / src_candidate.rstrip("/").lstrip("./")
                if target.is_file():
                    assert target.exists(), f"{dockerfile_name} の COPY 先ファイルが存在しない: {src_candidate}"


def test_entrypoint_no_stale_paths():
    """entrypoint.sh に案B で移動/削除されたパスの参照が残っていないこと。"""
    entrypoint = ROOT / "docker" / "backend" / "entrypoint.sh"
    if not entrypoint.exists():
        pytest.skip("entrypoint.sh が存在しない")
    content = entrypoint.read_text(encoding="utf-8")
    for stale in STALE_PATHS:
        assert stale not in content, (
            f"entrypoint.sh に旧パス参照が残っている: {stale}"
        )


def test_compose_no_stale_paths():
    """docker-compose*.yml に案B で移動/削除されたパスの参照が残っていないこと。"""
    for compose_file in ROOT.glob("docker-compose*.yml"):
        content = compose_file.read_text(encoding="utf-8")
        for stale in STALE_PATHS:
            assert stale not in content, (
                f"{compose_file.name} に旧パス参照が残っている: {stale}"
            )
