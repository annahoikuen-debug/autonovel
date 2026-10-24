"""Tests for MCP Proposal 2 (Deterministic Pre-Audit) and Proposal 9 (Novel Formatter & Linter)."""

from __future__ import annotations

import pytest

from src.mcp_servers.agent_mcp_bridge import AgentMCPBridge
from src.mcp_servers.audit_mcp_server import AuditMCPServer
from src.mcp_servers.providers.audit_provider import AuditProvider
from src.mcp_servers.providers.formatter_provider import NovelFormatterProvider
from src.agents.specialist_auditor_base import SpecialistAuditor


# --- Proposal 2: Deterministic Pre-Audit Screening Tests ---


def test_audit_provider_clean_text_bypass_eligible():
    """作法に問題がないテキストは高スコアで bypass_eligible=True となること。"""
    provider = AuditProvider()
    clean_text = "　夕暮れの空を見上げた。\n「行こう、時間がない」\n　二人は歩き出した……。"
    res = provider.pre_screen(clean_text)

    assert res.passed is True
    assert res.bypass_eligible is True
    assert res.score >= 90.0
    assert len(res.violations) == 0


def test_audit_provider_detects_all_stylistic_violations():
    """閉じ括弧不一致、奇数リーダー、会話文末句点、NGワードを確実に検知すること。"""
    provider = AuditProvider()
    provider.set_forbidden_words(["魔王城の秘密"])

    dirty_text = (
        "「開かないドアがある。\n"  # unclosed quotes
        "「これは危険だ。」\n"  # dialogue trailing period
        "沈黙が流れる…\n"  # odd ellipses
        "\n\n\n\n"  # excessive blank lines
        "魔王城の秘密が暴かれた。"  # forbidden word
    )
    res = provider.pre_screen(dirty_text)

    assert res.bypass_eligible is False
    rule_ids = {v.rule_id for v in res.violations}
    assert "unclosed_quotes" in rule_ids
    assert "dialogue_trailing_period" in rule_ids
    assert "odd_ellipses_or_dashes" in rule_ids
    assert "excessive_consecutive_blank_lines" in rule_ids
    assert "no_forbidden_words" in rule_ids


def test_audit_mcp_server_pre_screen_rpc():
    """AuditMCPServer が pre_screen メソッドを JSON-RPC で正しく処理すること。"""
    provider = AuditProvider()
    server = AuditMCPServer(provider)

    req = {
        "jsonrpc": "2.0",
        "method": "pre_screen",
        "params": {
            "text": "　風が吹き抜けた。\n「急ごう」",
            "specialist_name": "style",
            "bypass_threshold": 85.0,
        },
        "id": 101,
    }
    resp = server.handle_request(req)
    assert resp["id"] == 101
    assert "result" in resp
    assert resp["result"]["passed"] is True
    assert resp["result"]["bypass_eligible"] is True


@pytest.mark.asyncio
async def test_specialist_auditor_deterministic_pre_audit_bypass():
    """SpecialistAuditor が allow_pre_audit_bypass=True の場合、LLMを呼ばずに決定論的にパスすること。"""

    class DummySpecialist(SpecialistAuditor):
        specialist_name = "style"

        async def audit(self, ctx):
            raise AssertionError("LLM audit should not be called when bypassed!")

    auditor = DummySpecialist(llm=None)
    clean_ctx = {
        "text": "　朝日が昇った。\n「出発しよう」\n　彼らは旅立った……。",
        "allow_pre_audit_bypass": True,
    }

    result = await auditor.safe_audit(clean_ctx)
    assert result.degraded is False
    assert result.confidence == 1.0
    assert result.score >= 90.0
    assert result.feedback.get("deterministic_pre_audit") is True


# --- Proposal 9: Novel Formatter & Multi-Platform Linter Tests ---


def test_formatter_provider_typography_normalization():
    """地の文の字下げ、会話文の非字下げ、奇数三点リーダー補完、会話文末の句点除去。"""
    provider = NovelFormatterProvider()
    raw = "朝が来た。\n「早く起きてよ。」\n少女はため息をついた…\n\n\n\n\n　すでに街は動き出していた。"

    res = provider.format_novel(raw, platform="kakuyomu")
    lines = res.formatted_text.split("\n")

    # 地の文は全角字下げ
    assert lines[0].startswith("　朝が来た。")
    # 会話文は字下げなし & 末尾の『。』除去
    assert lines[1] == "「早く起きてよ」"
    # 三点リーダーは偶数個（……）
    assert "……" in res.formatted_text
    # 連続空行は最大2空行に圧縮
    assert "\n\n\n\n" not in res.formatted_text


def test_formatter_provider_platform_ruby_transpile():
    """プラットフォーム別のルビ記法変換テスト（なろう vs アルファポリス）。"""
    provider = NovelFormatterProvider()
    raw = "|灼熱《しゃくねつ》の炎"

    # カクヨム・なろう形式
    res_narou = provider.format_novel(raw, platform="narou")
    assert "|灼熱《しゃくねつ》の炎" in res_narou.formatted_text

    # アルファポリス形式
    res_alpha = provider.format_novel(raw, platform="alphapolis")
    assert "#灼熱(しゃくねつ)#の炎" in res_alpha.formatted_text


def test_formatter_provider_lint_novel():
    """作法リンターの検出テスト。"""
    provider = NovelFormatterProvider()
    flawed_text = "「開きっぱなしの括弧\n三点リーダー奇数…"
    lint_res = provider.lint_novel(flawed_text, platform="kakuyomu")

    assert lint_res.is_valid is False
    issue_types = [i.issue_type for i in lint_res.issues]
    assert "unbalanced_quotes" in issue_types
    assert "odd_ellipses" in issue_types


def test_formatter_provider_export_episode():
    """前書き・後書き・本文のエピソードパッケージング。"""
    provider = NovelFormatterProvider()
    res = provider.export_episode(
        title="第1話 旅立ち",
        content="彼らは旅立った。",
        platform="kakuyomu",
        foreword="読者の皆様こんにちは。",
        afterword="次回もお楽しみに！",
    )

    assert res["title"] == "第1話 旅立ち"
    assert "【前書き】" in res["full_package"]
    assert "【後書き】" in res["full_package"]
    assert "　彼らは旅立った。" in res["formatted_content"]


def test_agent_mcp_bridge_formatter_integration():
    """AgentMCPBridge を通じたフォーマッター呼び出しが正常に機能すること。"""
    bridge = AgentMCPBridge()
    raw = "走った。\n「待て。」"
    res = bridge.format_novel(raw, platform="kakuyomu")

    assert "formatted_text" in res
    assert "　走った。" in res["formatted_text"]
    assert "「待て」" in res["formatted_text"]
