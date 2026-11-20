"""GitHub Actions ワークフローファイルの YAML 構文リグレッション。

背景（2026-11-21 review-loop で発見）:
    72d87e3d で ci.yml の inline python スクリプトの block scalar インデントが
    欠落し、以降の全コミットで ci.yml が YAML パースエラーになっていた。
    GitHub Actions は構文エラーのワークフローを登録できず、**CI が一度も
    発火しない**状態が続いた（ローカルの `make ci-parity` は workflow ファイルを
    経由しないため全員気づかなかった）。

    本テストは「workflow ファイルがパース可能であること」を恒久検査し、
    同種の事故をテストジョブ内で検出する。
"""

from __future__ import annotations

import glob

import yaml

WORKFLOW_DIR = ".github/workflows"


def _workflow_files() -> list[str]:
    return sorted(
        p
        for p in glob.glob(f"{WORKFLOW_DIR}/*.yml") + glob.glob(f"{WORKFLOW_DIR}/*.yaml")
        if not p.endswith((".yml.bak", ".yaml.bak"))
    )


def test_workflow_dir_exists():
    files = _workflow_files()
    assert files, f"{WORKFLOW_DIR} 配下にワークフローファイルが存在しない"


def test_all_workflows_are_valid_yaml():
    """全 workflow ファイルが YAML としてパース可能であること。

    1 ファイルでも壊れると GitHub Actions はワークフローを登録できず、
    push / PR しても CI が一切発火しなくなる。
    """
    broken: list[str] = []
    for path in _workflow_files():
        try:
            with open(path, encoding="utf-8") as f:
                yaml.safe_load(f)
        except yaml.YAMLError as e:
            broken.append(f"{path}: {str(e).splitlines()[0]}")
    assert not broken, "YAML 構文エラーの workflow ファイルがあります:\n" + "\n".join(broken)


def test_ci_workflow_has_expected_jobs():
    """ci.yml が主要ジョブを保持していること（うっかり削除防止）。"""
    with open(f"{WORKFLOW_DIR}/ci.yml", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    jobs = set(doc.get("jobs", {}).keys())
    for expected in (
        "static-analysis",
        "release-consistency",
        "test",
        "integration",
        "frontend",
    ):
        assert expected in jobs, f"ci.yml からジョブ {expected} が消えています"


def test_ci_workflow_triggers_on_main_push():
    """ci.yml が main / develop への push で発火する設定であること。

    on.push.branches が欠けると main 更新時に CI が走らなくなる。
    """
    with open(f"{WORKFLOW_DIR}/ci.yml", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    on_section = doc.get(True) or doc.get("on") or {}
    # PyYAML は `on` を真偽値 True キーとして読むことがある（YAML 1.1 の仕様）
    branches = (on_section.get("push") or {}).get("branches") or []
    assert "main" in branches, f"on.push.branches に main が無い: {branches}"
    assert "develop" in branches, f"on.push.branches に develop が無い: {branches}"
