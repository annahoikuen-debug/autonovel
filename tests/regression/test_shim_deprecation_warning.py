"""Phase R1: 全 shim が DeprecationWarning を発することの検証 (SHIM_REMOVAL_PLAN)。

* 静的検証: 全 shim のソースに ``warnings.warn(..., DeprecationWarning, ...)`` が
  含まれること（import 時に警告が出る構造であること）。
* 動的検証（サンプリング）: 未 import の shim を subprocess で読み込み、
  実際に DeprecationWarning が stderr に出ること。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config" / "shim_registry.json"

registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
SHIMS: list[str] = registry["shims"]


def test_registry_exists_and_empty_after_q3():
    """shim registry が存在し、PLAN_Q3 完了により 0 件であること。"""
    assert REGISTRY_PATH.exists(), "config/shim_registry.json が存在しない"
    assert len(SHIMS) == 0, f"shim registry は 0 件であるべきだが {len(SHIMS)} 件ある: {SHIMS}"


@pytest.mark.parametrize("shim_path", SHIMS)
def test_shim_contains_deprecation_warning(shim_path):
    """全 shim のソースに DeprecationWarning の発行コードが含まれること。"""
    p = ROOT / shim_path
    if not p.exists():
        pytest.skip(f"shim ファイルが存在しない（削除計画 Phase R3 済み等）: {shim_path}")
    content = p.read_text(encoding="utf-8", errors="ignore")
    assert "warnings.warn" in content, f"{shim_path} に warnings.warn がない"
    assert "DeprecationWarning" in content, (
        f"{shim_path} の warnings.warn が DeprecationWarning を発していない"
    )


def test_shim_warning_messages_do_not_self_reference():
    """警告メッセージが自パスを指していないこと（use X instead の X は新パス）。"""
    self_referencing = []
    for shim_path in SHIMS:
        p = ROOT / shim_path
        if not p.exists():
            continue
        content = p.read_text(encoding="utf-8", errors="ignore")
        import re

        m = re.search(r'"(\S+) is deprecated; use (\S+) instead"', content)
        if m and m.group(1) == m.group(2):
            self_referencing.append(shim_path)
    assert not self_referencing, (
        f"警告メッセージが自パスを指している shim: {self_referencing}"
    )


def test_shim_emits_deprecation_warning_dynamically():
    """動的検証（代表サンプリング）: subprocess import 時に DeprecationWarning が出る。"""
    # PLAN_Q3 完了により shim は 0 件。動的検証対象がない場合はスキップ。
    if not SHIMS:
        pytest.skip("shim registry が 0 件のため動的検証対象なし（PLAN_Q3 完了済み）")
    # import 済み可能性が低い代表的 shim を 3 件選ぶ
    # config.* は Phase R3-1 (Step 9-13) で全件削除対象のため、services 系から選ぶ
    candidates = SHIMS[:3]
    for mod in candidates:
        result = subprocess.run(
            [sys.executable, "-c", f"import {mod}"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=60,
        )
        stderr = result.stderr or ""
        assert "DeprecationWarning" in stderr, (
            f"{mod} の import 時に DeprecationWarning が出ていない。\n"
            f"stderr: {stderr[:500]}"
        )
