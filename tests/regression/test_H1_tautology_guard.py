"""テストファイルから「絶対に落ちない assert」を機械的に検出する。

検出パターン:
  - ``assert <expr> or <expr>`` で両辺が同一の事実を述べているもの
  - ``assert x is not None or x is None``
  - ``assert True`` / ``assert 1``
  - ``inspect.getsource(...)`` の結果に対する ``in`` 判定
  - ``assert "..." in open(<ソースファイル>).read()``
  - ``expect(1).toBe(1)`` / ``expect(1 + 1).toBe(2)``
  - ``as never``
"""
from __future__ import annotations

import glob
import os
import re

FORBIDDEN: list[tuple[str, str]] = [
    (r"^\s*assert\s+True\s*$", "assert True"),
    (r"^\s*assert\s+1\s*$", "assert 1"),
    (r"is not None or \w+\.is None", "x is not None or x is None"),
    (r"or None$", "assert ... or None"),
    (r"in inspect\.getsource", "inspect.getsource による文字列 grep"),
    (r"in open\([^)]*\.py[^)]*\)\.read\(\)", "ソースファイルを read して文字列 grep"),
    (r"^\s*expect\(1\)\.toBe\(1\)", "expect(1).toBe(1)"),
    (r"^\s*expect\(1 \+ 1\)\.toBe\(2\)", "expect(1+1).toBe(2)"),
    (r"as never\b", "as never による fixture 型無効化"),
]

# 正当な例外として明示的に許可するファイル（理由必須）
ALLOWLIST: dict[str, str] = {
    "tests/regression/test_H1_tautology_guard.py": "本テスト自身",
    # TODO(H1-3): 実検証に置き換える (tasks.py の prefetch キャンセル処理の関数呼び出し/mock 検証)
    "tests/contract/test_w6_prefetch_invalidation_wiring.py": "TODO(H1-3): getsource grep を callable / mock 検証に置換予定",
    # TODO(H1-3): 実検証に置き換える (40ep 商業サイクル統合テスト内の assert True)
    "tests/integration/test_40ep_commercial_lifecycle.py": "TODO(H1-3): assert True をライフサイクル完了ステータス検証に置換予定",
    # TODO(H1-3): 実検証に置き換える (オーケストレータ例外系テスト内の assert True)
    "tests/unit/agents/test_orchestrator_core.py": "TODO(H1-3): assert True を例外発生検証に置換予定",
}


def _test_files() -> list[str]:
    return [
        p for p in glob.glob("tests/**/*.py", recursive=True)
        if os.path.basename(p).startswith("test_")
    ]


def test_no_tautological_assert_in_test_suite():
    offenders: list[str] = []
    for path in _test_files():
        rel = path.replace("\\", "/")
        if rel in ALLOWLIST:
            continue
        for lineno, line in enumerate(open(path, encoding="utf-8", errors="ignore"), 1):
            for pattern, label in FORBIDDEN:
                if re.search(pattern, line):
                    offenders.append(f"{rel}:{lineno} {label} :: {line.strip()[:80]}")
    assert not offenders, (
        f"恒真 assert が {len(offenders)} 件ある:\n  " + "\n  ".join(offenders)
    )


def test_allowlist_entries_have_reasons():
    for path, reason in ALLOWLIST.items():
        assert reason.strip(), f"{path} の allowlist に理由が無い"
