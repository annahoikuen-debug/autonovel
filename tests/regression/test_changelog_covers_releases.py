"""CHANGELOG が直近のリリースタグをカバーしていることを検証する。

TRACK-R R4: CHANGELOG 自動化の回帰テスト。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG_PATH = ROOT / "CHANGELOG.md"


def _get_git_tags() -> list[str]:
    """タグ一覧を取得する（新しい順）."""
    import subprocess

    result = subprocess.run(
        ["git", "tag", "--sort=-version:refname"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return [t for t in result.stdout.splitlines() if t.strip()]


def test_changelog_exists():
    """CHANGELOG.md が存在すること."""
    assert CHANGELOG_PATH.exists(), "CHANGELOG.md が存在しません"


def test_changelog_has_unreleased_section():
    """CHANGELOG.md に [Unreleased] エントリが存在すること."""
    content = CHANGELOG_PATH.read_text(encoding="utf-8")
    assert re.search(r"^##\s*\[Unreleased\]", content, re.MULTILINE), (
        "CHANGELOG.md に [Unreleased] エントリが見つかりません。"
    )


def test_changelog_covers_recent_tags():
    """直近のリリースタグが CHANGELOG.md に存在すること."""
    tags = _get_git_tags()
    if not tags:
        pytest.skip("タグが見つかりません")

    content = CHANGELOG_PATH.read_text(encoding="utf-8")

    # 最新タグと、その1つ前のタグ（計2つ）をチェック
    recent_tags = tags[:2]
    for tag in recent_tags:
        assert re.search(rf"^##\s*\[{re.escape(tag)}\]", content, re.MULTILINE), (
            f"CHANGELOG.md にタグ [{tag}] のエントリが見つかりません。"
        )
