"""ルート直下に追跡中 .db ファイルが存在しないことを検証する。

TRACK-R R2: ルート直下の .db ファイルを storage/ へ集約するための回帰テスト。
git ls-files '*.db' が storage/ 配下のみを返すことを assert する。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_tracked_db_in_root():
    """ルート直下に git 追跡中の .db ファイルが存在しないこと."""
    result = subprocess.run(
        ["git", "ls-files", "*.db"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    db_files = [line for line in result.stdout.splitlines() if line.strip()]
    root_db_files = [f for f in db_files if "/" not in f and "\\" not in f]
    assert not root_db_files, (
        f"ルート直下に追跡中 .db ファイルが存在します: {root_db_files}\n"
        "storage/ 配下に移動するか、.gitignore に追加してください。"
    )


def test_gitignore_includes_db():
    """.gitignore に *.db が記載されていること."""
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.db" in gitignore, (
        ".gitignore に *.db が記載されていません。"
        "ルート直下の .db ファイルが誤ってコミットされるのを防ぐため、"
        ".gitignore に *.db を追加してください。"
    )
