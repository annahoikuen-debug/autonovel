"""planning_options の FE スナップショットが Reality と一致することの回帰テスト。

FE テストが「自分で作ったモック」を使うため、実 API との乖離が検出できない
問題（カード選択ハイライト無効・成長曲線混入）の構造的原因を断つ。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SNAPSHOT = Path("frontend/tests/fixtures/planning_options.snapshot.json")


def test_snapshot_file_exists():
    assert SNAPSHOT.exists(), (
        f"{SNAPSHOT} が無い。`python scripts/export_planning_options.py` で生成せよ"
    )


def test_snapshot_matches_live_endpoint():
    """**スナップショットが現在のレスポンスと一致すること**（CI が緑なら必ず一致）。"""
    proc = subprocess.run(
        [sys.executable, "scripts/export_planning_options.py", "--check"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, (
        f"スナップショットが Reality と不一致。\n{proc.stdout}\n{proc.stderr}"
    )
