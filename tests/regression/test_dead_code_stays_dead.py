"""削除済みモジュールの復活を検出する回帰テスト。

PLAN_Q2 Step 3 による。`config/removed_modules.json` に登録されたモジュールが
`git ls-files` で追跡されていないことを確認し、削除済みモジュールの復活を
防ぐ。PLAN_R3 の test_shim_removal_detection.py と同様、集合一致ベースライン
方式で運用する（増加も減少も fail）。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _tracked_files() -> set[str]:
    """git ls-files で追跡済みすべてのファイルの相対パス集合を返す。

    Python モジュールだけでなく、Python ツリー内に紛れ込んだ React フォーク
    (.tsx / .ts) も含めて復活を検出する。
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        pytest.skip("git が利用できないためスキャンをスキップします")
    return {f for f in result.stdout.split("\0") if f}


def test_dead_code_stays_dead() -> None:
    """removed_modules.json に登録されたモジュールが復活していないこと。"""
    removed = json.loads((REPO_ROOT / "config" / "removed_modules.json").read_text(encoding="utf-8"))
    modules = removed.get("modules", [])
    tracked = _tracked_files()

    resurrected: list[str] = []
    for module in modules:
        # src.llm.clients.gemini → src/llm/clients/gemini.py
        # src.components.editor.Editor → src/components/editor/Editor.tsx
        path_py = module.replace(".", "/") + ".py"
        path_tsx = module.replace(".", "/") + ".tsx"
        path_ts = module.replace(".", "/") + ".ts"
        if path_py in tracked or path_tsx in tracked or path_ts in tracked:
            resurrected.append(module)

    assert not resurrected, (
        "削除済みモジュールが復活しています（git で追跡されています）: "
        f"{resurrected}\n"
        "復活が意図的な場合は config/removed_modules.json から該当エントリを削除し、"
        "ドキュメントを更新してください。"
    )
