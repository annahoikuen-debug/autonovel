"""CI ワークフローが「静かに壊れない」ための契約テスト。

現状 ``static-analysis`` ジョブは ``continue-on-error: true`` で記録のみ。
ruff/mypy の警告が「数」としてしか残らない状態だった。
本テストは「ratchet が hard gate として入っていること」を保証する。
"""
from __future__ import annotations

import re

WORKFLOW = ".github/workflows/ci.yml"


def _src() -> str:
    return open(WORKFLOW, encoding="utf-8").read()


def _job_block(name: str) -> str:
    src = _src()
    m = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z-]+:\n|\Z)", src, re.M | re.S)
    assert m, f"ジョブ {name} が ci.yml に無い"
    return m.group(1)


def test_lint_ratchet_is_a_hard_gate():
    block = _job_block("static-analysis")
    assert "continue-on-error: true" not in block, (
        "static-analysis が依然として continue-on-error のみ。ratchet を hard gate にしてほしい"
    )
    assert "ci_lint_ratchet.py" in block, "ratchet スクリプトが CI で実行されていない"


def test_lint_ratchet_baseline_is_tracked():
    import subprocess

    out = subprocess.run(["git", "ls-files", "config/ci_lint_baseline.json"],
                         capture_output=True, text=True)
    assert "config/ci_lint_baseline.json" in out.stdout, "ベースラインが追跡されていない"
