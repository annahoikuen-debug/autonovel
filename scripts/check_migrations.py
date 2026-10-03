#!/usr/bin/env python3
"""Alembic マイグレーション双方向（upgrade -> downgrade -> upgrade）自動検証スクリプト。"""
import os
import sys
import subprocess
from pathlib import Path


def run_command(cmd: list[str], env: dict[str, str] | None = None) -> bool:
    print(f"[RUN] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"[ERROR] Command failed with code {result.returncode}:")
        print(result.stderr)
        return False
    print(result.stdout)
    return True


def main() -> int:
    # alembic.ini はリポジトリルートにしか無く、script_location = src/backend/alembic も
    # ルート相対なので、必ずルートで実行する（他の場所から実行すると
    # "ERROR: Can't locate a configuration file" で落ちる）。test_db もルート直下に作る。
    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)

    test_db = project_root / "test_migration.db"
    if test_db.exists():
        test_db.unlink()

    env = os.environ.copy()
    # src/backend/alembic/env.py:20 が読むのは ALEMBIC_DATABASE_URL であり、
    # DATABASE_URL ではない。DATABASE_URL だけ設定すると env.py が
    # alembic.ini:4 の `sqlite:///./autonovel.db` (= 開発者の実 DB) に
    # フォールバックし、この往復チェックが開発 DB を破壊していた。
    env["ALEMBIC_DATABASE_URL"] = f"sqlite:///{test_db.resolve()}"
    # env.py 側の database.py 初期化経路にも同じ throwaway DB を向けさせる。
    env["DATABASE_URL"] = f"sqlite:///{test_db.resolve()}"

    print("Step 1: Upgrading to head...")
    if not run_command(["alembic", "upgrade", "head"], env=env):
        return 1

    print("Step 2: Downgrading 1 revision...")
    if not run_command(["alembic", "downgrade", "-1"], env=env):
        return 1

    print("Step 3: Re-upgrading to head...")
    if not run_command(["alembic", "upgrade", "head"], env=env):
        return 1

    if test_db.exists():
        test_db.unlink()

    print("SUCCESS: Migration roundtrip verified successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
