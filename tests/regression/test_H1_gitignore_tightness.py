"""追跡対象に残るスクラッチディレクトリを検出する。

``tests/regression/test_repo_hygiene.py`` の FORBIDDEN は特定ファイル名のみで
``tmp/`` 全体を見ていなかったため、43 件のスクラッチが追跡されたまま緑になっていた。
"""
from __future__ import annotations

import subprocess

SCRATCH_DIRS = ("tmp", "logs", "output", "artifacts")


def _tracked_files() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    )
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def test_no_scratch_dir_is_tracked():
    tracked = _tracked_files()
    offenders = sorted(
        f for f in tracked
        if any(f == d or f.startswith(d + "/") for d in SCRATCH_DIRS)
    )
    assert not offenders, (
        f"{len(offenders)} 件のスクラッチファイルが git 追跡下にある: {offenders[:20]}"
    )


def test_repo_hygiene_forbidden_list_covers_tmp():
    src = open("tests/regression/test_repo_hygiene.py", encoding="utf-8").read()
    assert "tmp" in src, "test_repo_hygiene.py の FORBIDDEN に tmp が無い"
