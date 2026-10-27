"""README / CHANGELOG の数値・記載が実測値と矛盾しないことの回帰テスト。

T6 Step 18 の回帰防止。

親計画 Step 35 は部分実施だった（CHANGELOG の 6.0.0 エントリは良いが、
`pyproject` 等が 5.3.0 のまま）。本テストは docs 側の同期を固定する。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _version() -> str:
    data = tomllib.loads(_read("pyproject.toml"))
    return str(data["project"]["version"])


def test_readme_version_matches_pyproject():
    version = _version()
    readme = _read("README.md")
    assert f"version-{version}" in readme, f"README のバッジが {version} でない"
    assert f"releases/tag/v{version}" in readme


def test_changelog_has_t6_entry_with_key_fixes():
    """6.0.0 エントリに T6 是正の主要項目が記載されていること。"""
    changelog = _read("CHANGELOG.md")
    assert "## [6.0.0]" in changelog, "CHANGELOG に 6.0.0 エントリが無い"
    entry = changelog.split("## [6.0.0]", 1)[-1].split("\n## [", 1)[0]
    for keyword in ("二重実行", "logger", "効果測定", "PLAN_T6_REMEDIATION_18STEPS"):
        assert keyword in entry, f"6.0.0 エントリに「{keyword}」の記載が無い"


def test_readme_documents_finalize_single_execution():
    """二重実行の修正と1話1回であることが README に明記されていること。"""
    readme = _read("README.md")
    assert "test_episode_finalize_called_once.py" in readme, (
        "README にダイジェスト二重実行の回帰テストが参照されていない"
    )
    digest_section = readme.split("ダイジェスト cost", 1)[-1][:2000]
    assert "2回" in digest_section, (
        "二重実行の事実が README に記載されていない"
    )


def test_readme_llm_calls_matches_measured_value():
    """README の1話LLM回数（10回）が docs/STATUS.md の実測値と一致すること。

    `docs/STATUS.md` §5.1 が唯一の出典。ここが唯一のチェック点。
    """
    readme = _read("README.md")
    status = _read("docs/STATUS.md")
    m = re.search(r"\|\s*1話あたり LLM 呼出回数\s*\|\s*10\s*\|", status)
    assert m is not None, (
        "docs/STATUS.md §5.1 に 1話LLM回数の実測値（10）が無い"
    )
    assert "10 回" in readme, "README に 1話10回の実測値が記載されていない"
    # 目標未達であることが両方で明示されていること
    assert "未達" in status, "docs/STATUS.md に未達の記載が無い"
    assert "未達" in readme, "README に未達の記載が無い"


def test_no_legacy_5_3_0_claims():
    """旧バージョンを正として主張していないこと。"""
    for rel in ("README.md", "docs/STATUS.md"):
        text = _read(rel)
        assert "version-5.3.0" not in text, f"{rel} に旧バージョンのバッジが残存"
    status = _read("docs/STATUS.md")
    assert "**5.3.0**" not in status, "docs/STATUS.md のバージョン節が旧版"
