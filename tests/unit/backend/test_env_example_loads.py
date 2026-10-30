"""`.env.example` がそのまま `Settings` で読み込めることの回帰テスト。

README は `cp .env.example .env` を案内している。`extra="forbid"` の設定に
対して example 側だけキーが増えると、利用者は起動時に ValidationError で
止まってしまうため、テンプレートのロード可否を機械的に固定する。
"""
from __future__ import annotations

from pathlib import Path

from src.backend.config import Settings

ROOT = Path(__file__).resolve().parents[3]


def test_env_example_loads_without_extra_forbidden_errors():
    settings = Settings(_env_file=ROOT / ".env.example")
    assert settings.APP_ENV in {"development", "testing", "production", "local", "staging"}
    # Docker Compose 用の値も Settings が受け止める（アプリは DATABASE_URL を使う）
    assert settings.POSTGRES_DB == "autonovel"
