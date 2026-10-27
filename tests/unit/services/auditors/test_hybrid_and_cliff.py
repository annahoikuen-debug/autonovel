"""services/auditors: TwoTierAuditor / CliffhangerScorer / 伏線監査の追加カバレッジ。"""

from __future__ import annotations

import pytest

from src.models.opening_booster import CliffhangerType
from src.services.auditors.cliffhanger_scorer import score_cliffhanger
from src.services.auditors.foreshadowing_auditor import (
    audit_foreshadowings,
    validate_foreshadowing_order,
)
from src.services.auditors.hybrid_auditor import TwoTierAuditor
from src.services.auditors.rule_based_metrics import (
    calculate_dialogue_ratio,
    calculate_kanji_ratio,
    calculate_sentence_rhythm,
    detect_ai_cliches,
    evaluate_cliffhanger_ending,
    verify_character_suffixes,
)


class _FakeQual:
    overall_score = 80.0
    hook_score = 71.0
    character_consistency = 82.0
    emotional_score = 66.0
    actionable_patch = "patch it"


class _FakeAuditor:
    def __init__(self, cliches):
        self._cliches = cliches

    def audit_quantitative(self, text):
        return 90.0, {"cliches": self._cliches}

    async def audit_qualitative(self, text, character_profiles="", plot_spec=""):
        return _FakeQual()


class _LowFakeQual(_FakeQual):
    overall_score = 40.0


async def test_two_tier_auditor_pass(monkeypatch):
    monkeypatch.setattr(
        "src.services.auditors.hybrid_auditor.UnifiedAuditor", lambda: _FakeAuditor([])
    )
    report = await TwoTierAuditor.audit_chapter("晴れた朝の物語。", forbidden_words=None)
    assert report.static_audit.passed is True
    assert report.qualitative_audit.score == 80
    assert "Hook score: 71.0" in report.qualitative_audit.pacing_comment
    assert "Character consistency: 82.0" in report.qualitative_audit.character_voice_comment
    assert "Emotional score: 66.0" in report.qualitative_audit.entertaining_hook_comment
    assert report.qualitative_audit.suggested_patch == "patch it"
    assert report.final_decision == "pass"
    assert report.static_audit.execution_time_ms >= 0.0


async def test_two_tier_auditor_forbidden_word(monkeypatch):
    monkeypatch.setattr(
        "src.services.auditors.hybrid_auditor.UnifiedAuditor", lambda: _FakeAuditor([])
    )
    report = await TwoTierAuditor.audit_chapter("これはNGワードを含む。", forbidden_words=["NGワード", "無い"])
    assert report.static_audit.passed is False
    assert len(report.static_audit.issues) == 1
    assert report.static_audit.issues[0].rule_id == "forbidden_word"
    assert report.static_audit.issues[0].severity == "error"
    assert report.final_decision == "patch_required"


async def test_two_tier_auditor_cliche_overload(monkeypatch):
    monkeypatch.setattr(
        "src.services.auditors.hybrid_auditor.UnifiedAuditor",
        lambda: _FakeAuditor(["a", "b", "c"]),
    )
    report = await TwoTierAuditor.audit_chapter("本文", forbidden_words=[])
    assert report.static_audit.passed is False
    assert report.final_decision == "patch_required"


async def test_two_tier_auditor_low_score(monkeypatch):
    class _Low(_FakeAuditor):
        def __init__(self):
            super().__init__([])
        async def audit_qualitative(self, text, character_profiles="", plot_spec=""):
            return _LowFakeQual()

    monkeypatch.setattr("src.services.auditors.hybrid_auditor.UnifiedAuditor", _Low)
    report = await TwoTierAuditor.audit_chapter("本文")
    assert report.static_audit.passed is True
    assert report.qualitative_audit.score == 40
    assert report.final_decision == "patch_required"


async def test_two_tier_auditor_empty_patch(monkeypatch):
    class _NoPatch(_FakeQual):
        actionable_patch = None

    class _A(_FakeAuditor):
        def __init__(self):
            super().__init__([])
        async def audit_qualitative(self, text, character_profiles="", plot_spec=""):
            return _NoPatch()

    monkeypatch.setattr("src.services.auditors.hybrid_auditor.UnifiedAuditor", _A)
    report = await TwoTierAuditor.audit_chapter("本文")
    assert report.qualitative_audit.suggested_patch == ""


def test_score_cliffhanger_empty():
    res = score_cliffhanger("   ")
    assert res.hook_type == CliffhangerType.PEACEFUL
    assert res.score == 0.0
    assert res.requires_rewrite is True
    assert res.tail_sentence == ""


def test_score_cliffhanger_peaceful():
    res = score_cliffhanger("今日はおやすみ。眠りに落ちた。")
    assert res.hook_type == CliffhangerType.PEACEFUL
    assert res.score == 35.0
    assert res.requires_rewrite is True


def test_score_cliffhanger_crisis():
    res = score_cliffhanger("背後から刃が飛んで来た。")
    assert res.hook_type == CliffhangerType.CRISIS
    assert res.score >= 80.0
    assert res.requires_rewrite is False
    assert res.tail_sentence


def test_score_cliffhanger_symbol_only():
    res = score_cliffhanger("彼は立ち止まった……")
    assert res.hook_type == CliffhangerType.CRISIS
    assert res.score == 65.0
    assert res.requires_rewrite is True


def test_score_cliffhanger_flat():
    res = score_cliffhanger("彼は静かに本を閉じた。")
    assert res.hook_type == CliffhangerType.PEACEFUL
    assert res.score == 40.0


def test_score_cliffhanger_only_200_tail_used():
    filler = "あ" * 500
    res = score_cliffhanger(filler + "侵入者が現れた。")
    assert res.hook_type == CliffhangerType.CRISIS


def test_validate_foreshadowing_order():
    assert validate_foreshadowing_order(1, 3) is True
    assert validate_foreshadowing_order(2, 2) is True
    assert validate_foreshadowing_order(4, 1) is False


def test_audit_foreshadowings_clean():
    res = audit_foreshadowings([{"title": "A", "planted_episode": 1, "resolved_episode": 2}], 3)
    assert res.is_valid is True
    assert res.total_issues == 0
    assert "問題はありません" in res.summary


def test_audit_foreshadowings_order_violation():
    res = audit_foreshadowings([{"title": "B", "planted_episode": 5, "resolved_episode": 2}], 6)
    assert res.is_valid is False
    assert len(res.order_violations) == 1
    assert "順序矛盾" in res.order_violations[0]
    assert "1件" in res.summary


def test_audit_foreshadowings_stale_and_overdue():
    items = [
        {"title": "C", "planted_episode": 1, "status": "planted"},
        {"title": "D", "planted_episode": 5, "status": "progressed", "target_episode": 6},
    ]
    res = audit_foreshadowings(items, 30, stale_threshold=15)
    assert len(res.stale_warnings) == 3
    assert any("長期未回収" in w for w in res.stale_warnings)
    assert any("期限超過" in w for w in res.stale_warnings)
    assert "警告: 3件" in res.summary


def test_audit_foreshadowings_object_and_defaults():
    class F:
        title = "E"
        planted_episode = 2
        resolved_episode = None
        status = "resolved"
        target_episode = None

    res = audit_foreshadowings([F()], 100, stale_threshold=5)
    assert res.total_issues == 0

    class Blank:
        pass

    res2 = audit_foreshadowings([Blank()], 3, stale_threshold=10)
    assert res2.total_issues == 0


def test_rule_based_metrics_empty_inputs():
    assert calculate_sentence_rhythm("") == (0, 0.0, 0.0, 50.0)
    assert calculate_dialogue_ratio("  \n\t").ratio == 0.0
    assert calculate_dialogue_ratio("").score == 50.0
    assert calculate_kanji_ratio("   ") == 0.0
    assert calculate_kanji_ratio("漢字abc") == pytest.approx(0.4)
    assert verify_character_suffixes([], ["x"]) == 100.0
    assert verify_character_suffixes(["a"], []) == 100.0


def test_rule_based_metrics_dialogue_bands():
    low = calculate_dialogue_ratio("あ" * 100)
    assert low.score < 100.0
    high = calculate_dialogue_ratio("「" + "あ" * 20 + "」")
    assert high.ratio > 0.45
    assert high.score >= 20.0


def test_detect_ai_cliches_hits_all():
    text = "〜だったのだ。言葉を失った。胸の奥底で。運命の歯車が。一筋の光が。予感を禁じ得なかった。何かが始まろうとしていた。"
    found = detect_ai_cliches(text)
    assert len(found) == 7


def test_evaluate_cliffhanger_ending_bonus():
    assert evaluate_cliffhanger_ending("ただの終わり。") == 50.0
    assert evaluate_cliffhanger_ending("その時、現れた者。") == 65.0
    assert evaluate_cliffhanger_ending("信じられない！") == 85.0
    assert evaluate_cliffhanger_ending(".sync") == 50.0
    assert evaluate_cliffhanger_ending(" ending 」") == 65.0
