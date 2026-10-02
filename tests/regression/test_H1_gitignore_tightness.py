"""追跡対象に残るスクラッチディレクトリを検出する。

``tests/regression/test_repo_hygiene.py`` の FORBIDDEN は特定ファイル名のみで
``tmp/`` 全体を見ていなかったため、43 件のスクラッチが追跡されたまま緑になっていた。

方針（R1 で実測して確定）:
- ``tmp/``・``logs/``・``output/``（.gitkeep 以外）は使い捨てなので追跡しない。
- ``artifacts/`` は**回帰防止テストの入力となる基準値**なので追跡を続ける
  （``.gitignore:112`` に明記済み）。ここは意図的に許可する。
"""
from __future__ import annotations

import subprocess

SCRATCH_DIRS = ("tmp", "logs", "output")

# 追跡を許すファイル（理由 必须）。
TRACKED_ALLOWLIST: dict[str, str] = {
    "output/.gitkeep": (
        "空ディレクトリを git に持たせるための慣習的なマーカー。"
        "TODO(H1-7): なし（git の慣習として恒久的に必要）"
    ),
}

# 追跡を許すディレクトリ（理由 必须）。
TRACKED_DIR_ALLOWLIST: dict[str, str] = {
    "artifacts": (
        "db_schema_baseline.json / test_baseline.json など回帰防止テストの入力"
        "（.gitignore:112 に明記）。TODO(H1-7): なし（テスト入力として恒久的に必要）"
    ),
}


def _tracked_files() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    )
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def test_no_scratch_dir_is_tracked():
    tracked = _tracked_files()
    offenders = sorted(
        f
        for f in tracked
        if f not in TRACKED_ALLOWLIST
        and not f.startswith(tuple(d + "/" for d in TRACKED_DIR_ALLOWLIST))
        and any(f == d or f.startswith(d + "/") for d in SCRATCH_DIRS)
    )
    assert not offenders, (
        f"{len(offenders)} 件のスクラッチファイルが git 追跡下にある: {offenders[:20]}"
    )


def test_repo_hygiene_forbidden_list_covers_tmp():
    src = open("tests/regression/test_repo_hygiene.py", encoding="utf-8").read()
    assert "tmp" in src, "test_repo_hygiene.py の FORBIDDEN に tmp が無い"


def test_gitignore_covers_every_scratch_dir():
    """``.gitignore`` が SCRATCH_DIRS をすべて無視する設定を持つこと。"""
    ignored = open(".gitignore", encoding="utf-8").read()
    missing = sorted(d for d in SCRATCH_DIRS if f"{d}/" not in ignored)
    assert not missing, f".gitignore が無視していないスクラッチディレクトリ: {missing}"


def test_allowlist_entries_have_reasons():
    for path, reason in {**TRACKED_ALLOWLIST, **TRACKED_DIR_ALLOWLIST}.items():
        assert reason.strip(), f"{path} の allowlist に理由が無い"
        assert "TODO(H1-" in reason, (
            f"{path} の allowlist に TODO(H1-N) の番号が無い（§9: 数値外れ禁止）"
        )
