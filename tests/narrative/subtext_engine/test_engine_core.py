"""
Unit tests for SubtextEngine core processing (Step 5).
"""

from src.narrative.subtext_engine.engine import SubtextEngine
from src.narrative.subtext_engine.models import DialogueBlock
from src.narrative.subtext_engine.rules import RegexRule, RuleRegistry


def test_engine_processes_rules_in_priority_order():
    registry = RuleRegistry()
    # rule 1 adds suffix A
    r1 = RegexRule(
        rule_id="r1",
        pattern=r"START",
        replacement="START_A",
        priority=10,
    )
    # rule 2 adds suffix B to A
    r2 = RegexRule(
        rule_id="r2",
        pattern=r"START_A",
        replacement="START_AB",
        priority=20,
    )
    registry.register(r2)
    registry.register(r1)

    engine = SubtextEngine(registry=registry)
    blocks = [DialogueBlock(speaker="X", lines=["START"])]
    res = engine.process(blocks)

    assert res[0].lines == ["START_AB"]
    assert res[0].applied_rules == ["r1", "r2"]


def test_engine_final_flag_stops_same_or_lower_priority_rules():
    """``final=True`` は同一優先度以下のルールの実行を止める。

    旧挙動（チェーン全体を停止）是つとは限らず、ThreatSubtextRule (50) /
    ComplianceSubvertRule (60) が拡張ルール (80-115) を飢餓状態にして
    しまうため、「同値またはそれより低い優先度のみ」に限定された。
    """
    registry = RuleRegistry()
    # list_rules は (priority, id) 昇順なので、同優先度では id 順に評価される。
    # final ルール (id="r_a_final") が最初に評価され、以降の同優先度ルールが
    # すべて停止される。
    r1 = RegexRule(
        rule_id="r_a_final",
        pattern=r"STOP",
        replacement="STOPPED",
        priority=20,
        final=True,
    )
    r2 = RegexRule(
        rule_id="r_b_same_priority",
        pattern=r"STOPPED",
        replacement="SAME_SHOULD_NOT_EXECUTE",
        priority=20,
    )
    r3 = RegexRule(
        rule_id="r_c_same_priority",
        pattern=r"STOPPED",
        replacement="C_SHOULD_NOT_EXECUTE",
        priority=20,
    )
    registry.register(r1)
    registry.register(r2)
    registry.register(r3)

    engine = SubtextEngine(registry=registry)
    blocks = [DialogueBlock(speaker="Y", lines=["STOP"])]
    res = engine.process(blocks)

    assert res[0].lines == ["STOPPED"]
    assert res[0].applied_rules == ["r_a_final"]


def test_engine_final_flag_allows_higher_priority_rules():
    """優先度が高い拡張ルールは下位 ``final`` ルール後も実行される。

    ThreatSubtextRule (50) がマッチしても priority 80-115 の拡張ルールが
    適用され続けることを保証する回帰テスト。
    """
    registry = RuleRegistry()
    low_final = RegexRule(
        rule_id="threat",
        pattern=r"危",
        replacement="危ない",
        priority=50,
        final=True,
    )
    high_extension = RegexRule(
        rule_id="extension",
        pattern=r"危ない",
        replacement="危ない——Lang",
        priority=80,
    )
    registry.register(low_final)
    registry.register(high_extension)

    engine = SubtextEngine(registry=registry)
    blocks = [DialogueBlock(speaker="Y", lines=["危"])]
    res = engine.process(blocks)

    assert res[0].lines == ["危ない——Lang"]
    assert res[0].applied_rules == ["threat", "extension"]


def test_engine_report_generation():
    engine = SubtextEngine.create_default()
    blocks = [
        DialogueBlock(speaker="A", lines=["「はい」"]),
        DialogueBlock(speaker="B", lines=["「私は悲しい」"]),
    ]
    engine.process(blocks)
    report = engine.generate_report()

    assert report["total_blocks_processed"] == 2
    assert report["modified_blocks_count"] >= 1
    assert "rule_application_counts" in report
