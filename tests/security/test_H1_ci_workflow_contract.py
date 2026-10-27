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


def test_pytest_marker_filter_actually_exists():
    """``pytest.ini`` が宣言するマーカーが、実際の実行で除外されていること。"""
    ini = open("pytest.ini", encoding="utf-8").read()
    for marker in ("perf", "slow", "flaky"):
        assert f"{marker}:" in ini, f"pytest.ini が {marker} を宣言していない"

    wf = _src()
    m = re.search(r"pytest -q -m \"([^\"]+)\"", wf)
    assert m, "CI に -m フィルタが無い"
    expr = m.group(1)
    for marker in ("perf", "slow"):
        assert marker in expr, f"CI が {marker} を除外していない: {expr}"


def test_timeout_flag_is_installed_in_ci():
    """``pytest.ini:16`` が前提とする pytest-timeout が CI で導入されていること。"""
    wf = _src()
    assert "pytest-timeout" in wf, "CI が pytest-timeout を導入していない"


def test_release_consistency_runs_more_than_version_check():
    """hard gate として意味のあるテストが 1 本以上あること。"""
    block = _job_block("release-consistency")
    runs = re.findall(r"pytest\s+(\S+)", block)
    assert len(runs) >= 1, "regression テストが 1 本も実行されていない"
    # 静的チェック（外部依存なし）であることが保証されていること
    assert "tests/regression" in block or "test_v5_version_consistency" in block
    assert "test_tenant_fk_integrity.py" in block, "release-consistency が tenant_fk を検証していない"
    assert "test_H1_tautology_guard.py" in block, "release-consistency が tautology を検証していない"
    assert "test_server_route_mount_parity.py" in block, "release-consistency が route mount parity を検証していない"


def test_hard_gate_jobs_never_continue_on_error():
    """hard gate と宣言されているジョブに continue-on-error が無いこと。"""
    for job in ("release-consistency", "test", "frontend", "static-analysis"):
        block = _job_block(job)
        assert "continue-on-error: true" not in block, f"{job} が continue-on-error"


def test_frontend_job_runs_all_three_gates():
    block = _job_block("frontend")
    for cmd in ("npm run typecheck", "npm run lint", "npm run test:ci"):
        assert cmd in block, f"frontend ジョブが {cmd} を実行していない"


def test_makefile_verify_matches_ci_gates():
    """Makefile の verify と CI が乖離していないこと。"""
    mk = open("Makefile", encoding="utf-8").read()
    assert "verify:" in mk, "Makefile に verify ターゲットが無い"
    body = mk.split("verify:", 1)[1].split("\n\n")[0]
    for target in ("lint", "typecheck", "test"):
        assert target in body, (
            f"verify が {target} を呼んでいない"
        )



