"""T6 是正計画の完了条件が満たされ続けていることの回帰テスト。

T6 Step 16/17 の机械化。`scripts/verify_t6_plan.py` が
「どのステップが実装済みか」を AST ベースで判定するため、
 このスクリプトの結果が緑であることは各ステップの**実装が生きている**ことを意味する。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_t6_plan_all_steps_satisfied():
    """T6 計画の全完了条件が満たされていること。"""
    result = subprocess.run(
        [sys.executable, "scripts/verify_t6_plan.py"],
        capture_output=True, text=True, cwd=ROOT, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, f"検証スクリプトが失敗: {result.stderr}"
    out = result.stdout

    assert "NG  " not in out, f"未達の完了条件がある:\n{out}"
    assert "未達:" not in out, f"未達項目がある:\n{out}"

    # ステップ数が増減していないこと（検証スクリプト自体の改変検知）
    line = [ln for ln in out.splitlines() if ln.startswith("完了 ")]
    assert line, f"完了数の行が無い:\n{out}"
    total = int(line[0].split("/")[1].strip())
    done = int(line[0].split()[1].split("/")[0].strip())
    assert done == total == 28, (
        f"完了条件数が {done}/{total}。検証スクリプトの改変または"
        "ステップの追加・削除がないか確認すること"
    )
