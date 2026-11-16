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
    """ベースラインを実測より低くすると失敗すること（ratchet が機能していることの証明）。

    ruff は既に 0 件（床に達している）ため、mypy（実測 502 件）のベースラインを
    意図的に低く（400 件）設定し、ratchet が増加を検出して失敗することを確認する。
    """
    import json as _json
    backup = BASE.read_text(encoding="utf-8")
    try:
        data = _json.loads(backup)
        data["mypy_errors"] = 400  # 実測 502 件より低い（＝過小評価）
        BASE.write_text(_json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        p = subprocess.run(
            [sys.executable, "scripts/ci_lint_ratchet.py", "--tool", "mypy"],
            capture_output=True, text=True,
        )
        assert p.returncode == 1, f"ratchet が失敗していない: rc={p.returncode}\n{p.stdout}\n{p.stderr}"
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
