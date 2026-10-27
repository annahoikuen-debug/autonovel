"""ratchet が「実測 > ベースライン」で失敗することを保証する。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path("config/ci_lint_baseline.json")


def test_baseline_file_exists_and_is_int():
    data = json.loads(BASE.read_text(encoding="utf-8"))
    assert isinstance(data["ruff_errors"], int)
    assert data["ruff_errors"] >= 0


def test_ratchet_fails_when_baseline_is_understated(tmp_path):
    """ベースラインを 0 にすると必ず失敗すること（archer が機能していることの証明）。"""
    backup = BASE.read_text(encoding="utf-8")
    try:
        BASE.write_text(json.dumps({"ruff_errors": 0}), encoding="utf-8")
        p = subprocess.run(
            [sys.executable, "scripts/ci_lint_ratchet.py"],
            capture_output=True, text=True,
        )
        assert p.returncode == 1, f"ratchet が失敗していない: rc={p.returncode}\n{p.stdout}"
    finally:
        BASE.write_text(backup, encoding="utf-8")


def test_ratchet_passes_with_actual_baseline():
    backup = BASE.read_text(encoding="utf-8")
    try:
        p = subprocess.run(
            [sys.executable, "scripts/ci_lint_ratchet.py", "--update"], capture_output=True, text=True
        )
        assert p.returncode == 0
        p = subprocess.run([sys.executable, "scripts/ci_lint_ratchet.py"], capture_output=True, text=True)
        assert p.returncode == 0, p.stdout
    finally:
        BASE.write_text(backup, encoding="utf-8")
