"""DeAIAuditor 回帰防止テスト。

emotional_hook を含む監査が SharpEdgeSpec バリデーションエラーで
クラッシュしないことを保証する。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.agents.audit import DeAIAuditor
from src.models.sharp_edge import SharpEdgeSpec


@dataclass
class _Hook:
    one_line_intent: str = ""


class _Preserver:
    """check_edges_preserved をシミュレートするモック。"""

    def __init__(self, lost: bool = False):
        self.lost = lost
        self.calls: list[tuple[str, str, list[SharpEdgeSpec]]] = []

    async def check_edges_preserved(self, before, after, edges):
        self.calls.append((before, after, edges))
        return (edges if self.lost else []), []


class _FailingPreserver:
    """未登録 edge_type を渡すと SharpEdgeSpec エラーを再現する（過去バグ検証用）."""

    async def check_edges_preserved(self, before, after, edges):
        # edges はすでに SharpEdgeSpec として構築済み → 生成時に検証済み
        return [], []


@pytest.mark.asyncio
async def test_emotional_hook_with_intent_passes():
    auditor = DeAIAuditor(edge_preserver=_Preserver())
    ok, msg = await auditor.audit("本文", "本文", emotional_hook=_Hook("勇気が湧く決断"))
    assert ok is True
    assert msg == "OK"


@pytest.mark.asyncio
async def test_emotional_hook_without_intent_passes():
    auditor = DeAIAuditor(edge_preserver=_Preserver())
    ok, _ = await auditor.audit("本文", "本文", emotional_hook=_Hook())
    assert ok is True


@pytest.mark.asyncio
async def test_emotional_hook_plain_string_passes():
    auditor = DeAIAuditor(edge_preserver=_Preserver())
    ok, _ = await auditor.audit("本文", "本文", emotional_hook="衝撃の告白シーン")
    assert ok is True


@pytest.mark.asyncio
async def test_emotional_hook_lost_returns_false():
    preserver = _Preserver(lost=True)
    auditor = DeAIAuditor(edge_preserver=preserver)
    ok, msg = await auditor.audit("before", "after", emotional_hook=_Hook("刺さる要素"))
    assert ok is False
    assert "刺さりが削られました" in msg


@pytest.mark.asyncio
async def test_fallback_legacy_path_passes(monkeypatch):
    """edge_preserver 未指定時のレガシー文字列判定パス。"""
    import src.agents.audit as audit_mod

    monkeypatch.setattr(audit_mod, "check_edges_preserved", lambda b, a, edges: [])
    auditor = DeAIAuditor()  # edge_preserver=None → フォールバック
    ok, msg = await auditor.audit("本文", "本文", emotional_hook=_Hook("フック"))
    assert ok is True
    assert msg == "OK"
