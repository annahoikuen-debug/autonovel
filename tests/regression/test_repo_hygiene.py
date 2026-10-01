"""Regression test: repository hygiene — forbidden artifacts must stay untracked.

These files were once committed by accident and removed via `git rm --cached`:
  - `$null` at the repo root (PowerShell `> $null` redirect accident)
  - `frontend/vite.config.ts.timestamp-*.mjs` (Vite build temp file)
  - `logs/*.jsonl` (runtime logs)
  - `output/coverage*.json` (generated coverage payloads)
  - `output/{m5,probe_lines,branches_missing,failures_analysis}.txt` (scratch reports)

The test asserts on the TRACKED file set (`git ls-files`), so untracked local
copies are fine. Dependency-free, no network, no DB.
"""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# (gitignore-rule, tracked-glob, human label)
FORBIDDEN: list[tuple[str, str, str]] = [
    ("/$null", "$null", "PowerShell `> $null` accident file at repo root"),
    (
        "frontend/vite.config.ts.timestamp-*.mjs",
        "frontend/vite.config.ts.timestamp-*.mjs",
        "Vite build temp file",
    ),
    ("logs/*.jsonl", "logs/*.jsonl", "runtime log file"),
    ("output/coverage*.json", "output/coverage*.json", "generated coverage JSON"),
    ("output/coverage-*.json", "output/coverage*.json", "generated coverage JSON"),
    ("output/m5.txt", "output/m5.txt", "scratch analysis file"),
    ("output/probe_lines.txt", "output/probe_lines.txt", "scratch analysis file"),
    ("output/branches_missing.txt", "output/branches_missing.txt", "scratch analysis file"),
    ("output/failures_analysis.txt", "output/failures_analysis.txt", "scratch analysis file"),
    ("tmp/*", "tmp/*", "temporary scratch file"),
]

# Labels that must appear in .gitignore (one representative glob per class).
REQUIRED_GITIGNORE_RULES = [
    "/$null",
    "frontend/vite.config.ts.timestamp-*.mjs",
    "logs/*.jsonl",
    "output/coverage-*.json",
    "output/m5.txt",
    "output/probe_lines.txt",
    "output/branches_missing.txt",
    "output/failures_analysis.txt",
]


def _tracked_files() -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # git missing / timeout
        pytest.skip(f"git is unavailable: {exc}")
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        pytest.skip(f"not a git repository (git ls-files failed: {err})")
    stdout = proc.stdout.decode("utf-8", errors="replace")
    return [p for p in stdout.split("\0") if p]


def test_no_forbidden_artifacts_are_tracked():
    """None of the previously-committed junk files may be tracked again."""
    tracked = _tracked_files()
    if not tracked:
        pytest.skip("git ls-files returned no tracked files")

    violations: list[str] = []
    for _rule, glob, label in FORBIDDEN:
        for path in tracked:
            if fnmatch.fnmatch(path, glob):
                violations.append(f"{path}  ({label})")

    assert not violations, (
        "Forbidden artifacts are tracked in git. Untrack them with "
        "`git rm --cached <path>` and keep them ignored:\n  "
        + "\n  ".join(sorted(set(violations)))
    )


def test_gitignore_covers_forbidden_artifacts():
    """.gitignore must keep a rule for every class of forbidden artifact."""
    gitignore = REPO_ROOT / ".gitignore"
    assert gitignore.is_file(), f".gitignore is missing at {gitignore}"

    text = gitignore.read_text(encoding="utf-8", errors="replace")
    present = {line.strip() for line in text.splitlines()}
    missing = [rule for rule in REQUIRED_GITIGNORE_RULES if rule not in present]

    assert not missing, (
        ".gitignore is missing required ignore rules; add them so the forbidden "
        "artifacts cannot be re-committed:\n  " + "\n  ".join(missing)
    )
