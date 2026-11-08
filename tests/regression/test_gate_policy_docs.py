"""テストゲート運用ポリシーの文言遵守テスト.

docs/TEST_GATE_POLICY.md の「未達」定義・禁止語リスト、
.github/workflows/ci.yml のコメント、
docs/PLAN_C_SUMMARY.md の古い件数表記を検証する。
"""
from __future__ import annotations

from pathlib import Path

import pytest

CI_YML = Path(".github/workflows/ci.yml")
POLICY_MD = Path("docs/TEST_GATE_POLICY.md")
PLAN_C_SUMMARY = Path("docs/PLAN_C_SUMMARY.md")


def test_policy_md_exists_and_defines_three_states() -> None:
    assert POLICY_MD.is_file()
    text = POLICY_MD.read_text(encoding="utf-8")
    assert "green" in text
    assert "red" in text
    assert "未達" in text
    # 「未達」は failed 数 > 0 を意味する旨
    assert "failed" in text and "> 0" in text


def test_policy_md_has_prohibited_terms() -> None:
    text = POLICY_MD.read_text(encoding="utf-8")
    for term in ["観測", "既知失敗", "許容範囲"]:
        assert term in text, f"禁止語リストに '{term}' が含まれていない"


def test_ci_yaml_unreached_comment_when_continue_on_error_true() -> None:
    """continue-on-error: true が残っている間、統合ジョブ直前コメントに「未達」があること."""
    text = CI_YML.read_text(encoding="utf-8")
    if "continue-on-error: true" not in text:
        pytest.skip("continue-on-error: true が既に外れているためスキップ")
    idx = text.find("integration-observe:")
    assert idx != -1, "integration-observe ジョブが見つからない"
    block = text[:idx]
    assert "未達" in block, "continue-on-error: true の直前コメントに「未達」が書かれていない"


def test_plan_c_summary_no_old_count() -> None:
    """docs/PLAN_C_SUMMARY.md に古い件数「54 件の既知失敗」が残っていないこと."""
    assert PLAN_C_SUMMARY.is_file()
    text = PLAN_C_SUMMARY.read_text(encoding="utf-8")
    assert "54 件の既知失敗" not in text
