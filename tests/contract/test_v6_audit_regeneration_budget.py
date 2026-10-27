"""PDCA 予算により全滅再生成が1話1回に封じ込められることの回帰テスト。

W4 Step 10（``src/agents/audit_agent.py``）の契約テスト。

計画書からの逸脱（理由付き）:
- 計画書のテストは ``PDCAController.can_regenerate_full_text()`` を使っているが、
  実 API 名は ``should_regenerate_full_text()``（``src/generation/pdca_controller.py:29``）。
  ``pdca_controller.py`` は編集せず、テスト側を実 API 名に合わせた。
- 計画書の ``max_regenerations=0`` は「1話1回目の Branch D も封じ込める」ことになり、
  既存契約 ``test_v6_audit_gate_thresholds.py::test_critical_failure_triggers_regeneration``
  が赤くなる。本番配線は ``max_regenerations=1`` にしている（1回だけ通し、2回目で封じる）。
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agents.audit_agent import AuditAgent, is_repair_budget_enabled  # noqa: E402
from src.generation.pdca_controller import PDCAController  # noqa: E402


def test_budget_flag_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_AUDIT_REPAIR_BUDGET", raising=False)
    assert is_repair_budget_enabled() is True


def test_budget_flag_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AUDIT_REPAIR_BUDGET", "0")
    assert is_repair_budget_enabled() is False


def test_budget_allows_first_regeneration_then_blocks_second() -> None:
    c = PDCAController(max_regenerations=1, max_local_patches=3)
    assert c.should_regenerate_full_text() is True
    c.record_full_regeneration()
    assert c.regeneration_count == 1
    assert c.should_regenerate_full_text() is False


def test_budget_blocks_full_regeneration_when_zero_allowed() -> None:
    c = PDCAController(max_regenerations=0, max_local_patches=3)
    assert c.should_regenerate_full_text() is False
    c.record_full_regeneration()
    assert c.regeneration_count == 1


def test_local_patch_budget_counts_up() -> None:
    c = PDCAController(max_regenerations=0, max_local_patches=2)
    assert c.can_do_local_patch() is True
    c.record_local_patch()
    c.record_local_patch()
    assert c.can_do_local_patch() is False
    assert c.local_patch_count == 2


def test_reset_counts_restores() -> None:
    c = PDCAController(max_regenerations=1, max_local_patches=1)
    c.record_full_regeneration()
    c.record_local_patch()
    c.reset_counts()
    assert c.regeneration_count == 0
    assert c.local_patch_count == 0


def test_agent_budget_is_one_regeneration_and_three_patches() -> None:
    agent = AuditAgent()
    budget = agent._repair_budget
    assert budget.max_regenerations == 1
    assert budget.max_local_patches == 3
    assert budget.should_regenerate_full_text() is True


def test_pdca_controller_api_name_used_by_agent_exists() -> None:
    """``pdca_controller.py`` を編集せず、実メソッド名で配線できていることの爪。"""
    assert hasattr(PDCAController, "should_regenerate_full_text")
    assert not hasattr(PDCAController, "can_regenerate_full_text")
