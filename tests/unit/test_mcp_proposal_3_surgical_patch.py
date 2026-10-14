"""Tests for MCP Proposal 3: Surgical Patch & Local Diff Server."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.mcp_servers.agent_mcp_bridge import AgentMCPBridge
from src.mcp_servers.patch_server import PatchMCPServer
from src.mcp_servers.providers.patch_provider import SurgicalPatchProvider
from src.agents.specialist_auditor_base import ActionableDiff
from src.agents.writing.agent import WritingAgent


def test_surgical_patch_exact_match():
    """完全一致する ActionableDiff が本文に外科的に置換適用されること。"""
    provider = SurgicalPatchProvider()
    original = (
        "　エリスは静かに剣を抜いた。\n"
        "「お前を絶対に許さない」\n"
        "　冷徹な瞳が敵を射貫く。"
    )
    diffs = [
        ActionableDiff(
            location="第2行 セリフ",
            original_quote="「お前を絶対に許さない」",
            improved_suggestion="「……ここで終わらせる」",
            rationale="感情を抑えた静かな殺気を表現するため",
        )
    ]

    result = provider.apply_actionable_diffs(original, diffs)
    assert result.is_fully_applied is True
    assert result.applied_count == 1
    assert result.failed_count == 0
    assert "「……ここで終わらせる」" in result.patched_text
    assert "「お前を絶対に許さない」" not in result.patched_text
    # 修正箇所以外の文体は一切変わらないこと（リグレッションなし）
    assert "　エリスは静かに剣を抜いた。" in result.patched_text
    assert "　冷徹な瞳が敵を射貫く。" in result.patched_text


def test_surgical_patch_multiple_diffs_safe_replace():
    """複数の Diff が二重置換衝突を起こさずに1パスで安全適用されること。"""
    provider = SurgicalPatchProvider()
    original = "AからBへ移動した。そしてBからCへ向かった。"
    diffs = [
        {"location": "1", "original_quote": "A", "improved_suggestion": "B"},
        {"location": "2", "original_quote": "B", "improved_suggestion": "Z"},
    ]

    result = provider.apply_actionable_diffs(original, diffs)
    assert result.applied_count == 2
    # A->B, B->Z だが AがZに化けず、SafeReplacer で A->B, 元のB->Z となる
    assert "BからZへ移動した。そしてZからCへ向かった。" == result.patched_text


def test_surgical_patch_fuzzy_match():
    """軽微な空白差異があってもファジーマッチで安全に特定・置換できること。"""
    provider = SurgicalPatchProvider()
    original = "　彼女は振り返り、微笑んだ。"
    diffs = [
        ActionableDiff(
            location="末尾",
            original_quote="彼女は振り返り、 微笑んだ。",  # 空白が混ざっている
            improved_suggestion="彼女は切なげに微笑んだ。",
            rationale="哀愁の強調",
        )
    ]

    result = provider.apply_actionable_diffs(original, diffs, allow_fuzzy=True)
    assert result.applied_count == 1
    assert "切なげに微笑んだ" in result.patched_text


def test_extract_patch_windows():
    """指摘箇所のある段落前後がパッチウィンドウとして正確に切り出されること。"""
    provider = SurgicalPatchProvider()
    text = "\n".join([f"第{i}段落の文章です。" for i in range(1, 11)])

    windows = provider.extract_patch_windows(
        original_text=text,
        target_quotes=["第5段落の文章です。"],
        padding_lines=2,
    )

    assert len(windows) == 1
    w = windows[0]
    assert "第5段落の文章です。" in w.padded_context
    assert "第3段落" in w.padded_context
    assert "第7段落" in w.padded_context


def test_patch_mcp_server_rpc():
    """PatchMCPServer の JSON-RPC ハンドラーが正常に動作すること。"""
    server = PatchMCPServer()
    req = {
        "jsonrpc": "2.0",
        "method": "apply_actionable_diffs",
        "params": {
            "original_text": "古い文章です。",
            "diffs": [{"original_quote": "古い", "improved_suggestion": "新しい"}],
        },
        "id": 99,
    }
    resp = server.handle_request(req)
    assert resp["id"] == 99
    assert resp["result"]["patched_text"] == "新しい文章です。"
    assert resp["result"]["applied_count"] == 1


def test_agent_mcp_bridge_patch_integration():
    """AgentMCPBridge から外科的パッチが呼び出せること。"""
    bridge = AgentMCPBridge()
    original = "門が開いた。"
    diffs = [{"original_quote": "門が開いた。", "improved_suggestion": "重厚な門が軋みを上げて開いた。"}]
    res = bridge.apply_surgical_diffs(original, diffs)

    assert res["is_fully_applied"] is True
    assert "重厚な門が軋みを上げて開いた。" in res["patched_text"]


@pytest.mark.asyncio
async def test_writing_agent_rewrite_with_surgical_patch_bypass():
    """WritingAgent.rewrite_for_dimension が ActionableDiff を検知した場合、LLMを呼ばずに即座に置換すること。"""
    mock_repo = MagicMock()
    mock_chapter = MagicMock()
    mock_chapter.content = "朝が来た。\n「おはよう。」\n今日も一日が始まる。"
    mock_repo.get_chapter = AsyncMock(return_value=mock_chapter)

    # LLMが呼ばれたら例外を投げるようにモックして、バイパスされることを検証
    mock_llm = MagicMock()
    mock_llm.agenerate = AsyncMock(side_effect=AssertionError("LLM should not be called when surgical patch succeeds!"))

    agent = WritingAgent(repo=mock_repo, llm=mock_llm)
    diffs = [
        ActionableDiff(
            location="会話文",
            original_quote="「おはよう。」",
            improved_suggestion="「おはよう！」",
            rationale="元気を出すため",
        )
    ]

    result = await agent.rewrite_for_dimension(
        book_id=1,
        branch_id=1,
        ep_num=1,
        dimension="reader_experience",
        actionable_diffs=diffs,
    )

    assert result["status"] == "success"
    assert "「おはよう！」" in result["rewritten_text"]
    assert "朝が来た。" in result["rewritten_text"]
    assert "今日も一日が始まる。" in result["rewritten_text"]
