"""pyproject / README / CHANGELOG のバージョンが一致することの回帰テスト。

T6 Step 9 の回帰防止。

`CHANGELOG.md` に `[6.0.0]` エントリがあるのに `pyproject.toml` は
`5.3.0` のままだったため、**6.0.0 の CHANGELOG を持つ 5.3.0 のプロジェクト**
という自己矛盾になっていた（`test_v5_version_consistency.py` は pyproject を
正準とするため、矛盾が潜在化していた）。

本テストは「CHANGELOG の先頭エントリ == pyproject の version」を
明示的に固定する。
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_pyproject_version_is_v6():
    assert _pyproject_version() == "6.0.0"


def test_readme_badge_matches_pyproject():
    """README のバージョンバッジが SSOT と一致すること。"""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    version = _pyproject_version()
    assert f"version-{version}" in readme, (
        f"README の version バッジが {version} になっていない"
    )
    assert f"releases/tag/v{version}" in readme, (
        f"README のリリースリンクが v{version} になっていない"
    )


def test_changelog_top_entry_matches_pyproject():
    """CHANGELOG の先頭エントリが SSOT と一致すること（自己矛盾の防止）。"""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    top = re.search(r"^##\s*\[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)
    assert top is not None, "CHANGELOG に版数のエントリが無い"
    version = _pyproject_version()
    assert top.group(1) == version, (
        f"CHANGELOG 先頭は {top.group(1)} だが pyproject は {version}。"
        "PR を作る前に両者を揃えること"
    )


def test_no_stale_5_3_0_version_badge():
    """旧バージョンのバッジが残っていないこと。"""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "version-5.3.0-brightgreen" not in readme
