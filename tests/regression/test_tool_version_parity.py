"""CI とローカルの lint ツールバージョン整合を担保する契約テスト。

GitHub Actions (.github/workflows/ci.yml) と requirements.txt で
ruff / mypy のバージョンがずれると、ローカルと CI で型エラー・lint 件数が
乖離し、lint ratchet baseline が意味を失う。

実測: mypy 2.3.1 と 2.4.1 で型エラー件数が 126 件ずれることを確認済み。
"""

from __future__ import annotations

import re


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _pin_versions(text: str, tool: str) -> str:
    """`pip install "ruff==X" "mypy==Y"` または `ruff==X` 行からバージョンを抽出。"""
    m = re.search(rf"{tool}==([0-9]+\.[0-9]+\.[0-9]+)", text)
    if not m:
        raise AssertionError(f"{tool} のピンバージョンが見つかりません")
    return m.group(1)


def test_lint_tool_versions_match_ci() -> None:
    """ci.yml と requirements.txt の ruff/mypy バージョンが一致すること。"""
    ci_text = _read(".github/workflows/ci.yml")
    req_text = _read("requirements.txt")

    for tool in ("ruff", "mypy"):
        ci_ver = _pin_versions(ci_text, tool)
        req_ver = _pin_versions(req_text, tool)
        assert ci_ver == req_ver, (
            f"{tool} のバージョンが ci.yml ({ci_ver}) と "
            f"requirements.txt ({req_ver}) でずれています。どちらかに統一してください。"
        )
