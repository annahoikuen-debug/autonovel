"""src/narrative/subtext_engine/rules.py の単体テスト。"""
from __future__ import annotations

import re

import pytest

from src.narrative.subtext_engine.models import DialogueBlock, SubtextContext
from src.narrative.subtext_engine.rules import (
    AddressDistanceRule,
    CausalToIronyRule,
    ComplianceSubvertRule,
    EmotionToActionRule,
    ExplanatoryCompressRule,
    ExtensionRule,
    RegexRule,
    RuleBase,
    RuleRegistry,
    SubjectiveInternalizeRule,
    ThreatSubtextRule,
    create_extension_rules,
)


def block(*lines, speaker="A", applied=None):
    return DialogueBlock(
        speaker=speaker, lines=list(lines), applied_rules=list(applied or [])
    )


class TestRegexRule:
    def test_replaces(self):
        r = RegexRule("r1", r"a", "b")
        out = r.apply(block("aaa"))
        assert out.modified is True
        assert out.block.lines == ["bbb"]
        assert out.applied_rule_id == "r1"
        assert "modified text" in out.diff_summary

    def test_no_match(self):
        r = RegexRule("r1", r"z", "b")
        out = r.apply(block("aaa"))
        assert out.modified is False

    def test_disabled(self):
        r = RegexRule("r1", r"a", "b", enabled=False)
        assert r.apply(block("aaa")).modified is False

    def test_skip_if_matched(self):
        r = RegexRule("r1", r"a", "b", skip_if_matched=True)
        out = r.apply(block("aaa", applied=["r1"]))
        assert out.modified is False

    def test_empty_text(self):
        r = RegexRule("r1", r"a", "b")
        assert r.apply(block()).modified is False

    def test_callable_replacement(self):
        r = RegexRule("r1", r"(\d)", lambda m: f"[{m.group(1)}]")
        out = r.apply(block("a1b"))
        assert out.block.lines == ["a[1]b"]
        assert r.replacement_str == "<callable>"

    def test_compiled_pattern(self):
        r = RegexRule("r1", re.compile(r"a+"), "X")
        assert r.pattern_str == "a+"
        assert r.apply(block("aaa")).block.lines == ["X"]

    def test_error_in_substitution(self):
        class Boom:
            def __call__(self, m):
                raise ValueError("bad")

        r = RegexRule("r1", r"a", Boom())
        out = r.apply(block("aaa"))
        assert out.success is False
        assert "Regex error" in out.diff_summary

    def test_replacement_no_change(self):
        r = RegexRule("r1", r"a", "a")
        out = r.apply(block("aaa"))
        assert out.modified is False

    def test_multiline_split(self):
        r = RegexRule("r1", r"X", "Y")
        out = r.apply(block("aXb\ncXd"))
        assert out.block.lines == ["aYb", "cYd"]

    def test_to_model(self):
        m = RegexRule("r1", "a", "b", name="N", priority=5, final=True, tags=["t"]).to_model()
        assert m.id == "r1" and m.pattern == "a" and m.replacement == "b"
        assert m.priority == 5 and m.final is True and m.tags == ["t"]


class TestRuleRegistry:
    def setup_method(self):
        RuleRegistry.reset()
        self.reg = RuleRegistry.get_instance()

    def teardown_method(self):
        RuleRegistry.reset()

    def test_singleton(self):
        assert RuleRegistry.get_instance() is self.reg

    def test_register_and_get(self):
        r = RegexRule("r1", "a", "b")
        self.reg.register(r)
        assert self.reg.get("r1") is r

    def test_register_duplicate_raises(self):
        self.reg.register(RegexRule("r1", "a", "b"))
        with pytest.raises(ValueError):
            self.reg.register(RegexRule("r1", "c", "d"), overwrite=False)

    def test_register_overwrite(self):
        self.reg.register(RegexRule("r1", "a", "b"))
        r2 = RegexRule("r1", "c", "d")
        self.reg.register(r2, overwrite=True)
        assert self.reg.get("r1") is r2

    def test_unregister(self):
        self.reg.register(RegexRule("r1", "a", "b"))
        assert self.reg.unregister("r1") is not None
        assert self.reg.unregister("r1") is None

    def test_list_rules_sorted(self):
        self.reg.register(RegexRule("b", "a", "b", priority=5))
        self.reg.register(RegexRule("a", "a", "b", priority=5))
        self.reg.register(RegexRule("c", "a", "b", priority=1))
        assert [r.id for r in self.reg.list_rules()] == ["c", "a", "b"]

    def test_list_rules_enabled_only(self):
        self.reg.register(RegexRule("a", "a", "b", enabled=False))
        self.reg.register(RegexRule("b", "a", "b"))
        assert [r.id for r in self.reg.list_rules(enabled_only=True)] == ["b"]

    def test_clear(self):
        self.reg.register(RegexRule("a", "a", "b"))
        self.reg.clear()
        assert self.reg.list_rules() == []


class TestExplanatoryCompressRule:
    def test_compresses_three_lines(self):
        r = ExplanatoryCompressRule()
        out = r.apply(block("「a」", "「b」", "「c」"))
        assert out.modified is True
        assert len(out.block.lines) == 2
        assert out.block.lines[0].startswith("（")
        assert out.block.lines[1] == "「c」"

    def test_fewer_than_three(self):
        r = ExplanatoryCompressRule()
        assert r.apply(block("「a」", "「b」")).modified is False

    def test_disabled(self):
        r = ExplanatoryCompressRule()
        r.enabled = False
        assert r.apply(block("「a」", "「b」", "「c」")).modified is False

    def test_non_consecutive(self):
        r = ExplanatoryCompressRule()
        b = block("「a」", "ナレーション", "「b」", "「c」")
        assert r.apply(b).modified is False

    def test_two_sequences(self):
        r = ExplanatoryCompressRule()
        b = block("「a」", "「b」", "「c」", "x", "「d」", "「e」", "「f」")
        out = r.apply(b)
        assert out.modified is True
        assert len(out.block.lines) == 5

    def test_deterministic_with_context(self):
        r = ExplanatoryCompressRule()
        b = block("「a」", "「b」", "「c」")
        c1 = SubtextContext(turn_index=1)
        c2 = SubtextContext(turn_index=1)
        assert r.apply(b, c1).block.lines == r.apply(b, c2).block.lines


class TestEmotionToActionRule:
    def test_dialogue_with_emotion(self):
        r = EmotionToActionRule()
        out = r.apply(block("「彼女は悲しい」"))
        assert out.modified is True
        assert "——" in out.block.lines[0]

    def test_negation_skipped(self):
        r = EmotionToActionRule()
        assert r.apply(block("「悲しくない」")).modified is False

    def test_negation_variant_skipped(self):
        r = EmotionToActionRule()
        assert r.apply(block("「悲しくはない」")).modified is False

    def test_narration_line(self):
        r = EmotionToActionRule()
        out = r.apply(block("彼女は怒っている"))
        assert out.modified is True
        assert out.block.lines[0].endswith("。")

    def test_pure_emotion_dialogue(self):
        r = EmotionToActionRule()
        out = r.apply(block("「悲し」"))
        assert out.block.lines[0].startswith("（")

    def test_no_emotion(self):
        r = EmotionToActionRule()
        assert r.apply(block("「今日は晴れ」")).modified is False

    def test_disabled(self):
        r = EmotionToActionRule()
        r.enabled = False
        assert r.apply(block("「悲しい」")).modified is False

    def test_custom_actions(self):
        r = EmotionToActionRule(actions={"怒っ": "X"})
        out = r.apply(block("「怒っている」"))
        assert "X" in out.block.lines[0]


class TestCausalToIronyRule:
    def test_dialogue(self):
        r = CausalToIronyRule()
        out = r.apply(block("「なぜなら彼が来たからだ」"))
        assert out.modified is True
        assert out.block.lines[0].startswith("「……")

    def test_narration(self):
        r = CausalToIronyRule()
        out = r.apply(block("理由はこうだ"))
        assert out.block.lines[0].startswith("……")

    def test_no_match(self):
        r = CausalToIronyRule()
        assert r.apply(block("普通")).modified is False

    def test_disabled(self):
        r = CausalToIronyRule()
        r.enabled = False
        assert r.apply(block("理由はこうだ")).modified is False

    def test_custom_pool(self):
        r = CausalToIronyRule(irony_pool=["X"])
        out = r.apply(block("理由はこうだ"), SubtextContext(turn_index=0))
        assert "X" in out.block.lines[0]


class TestSubjectiveInternalizeRule:
    def test_matches(self):
        r = SubjectiveInternalizeRule()
        out = r.apply(block("「私は本当に思う」"))
        assert out.modified is True
        assert out.block.lines[0].startswith("（……")

    def test_no_match(self):
        r = SubjectiveInternalizeRule()
        assert r.apply(block("空の行")).modified is False

    def test_disabled(self):
        r = SubjectiveInternalizeRule()
        r.enabled = False
        assert r.apply(block("「俺は愛してる」")).modified is False


class TestThreatSubtextRule:
    def test_threat(self):
        r = ThreatSubtextRule()
        out = r.apply(block("「お前を殺してやる」"))
        assert out.modified is True
        assert "——" in out.block.lines[0]

    def test_no_threat(self):
        r = ThreatSubtextRule()
        assert r.apply(block("平和だ")).modified is False

    def test_disabled(self):
        r = ThreatSubtextRule()
        r.enabled = False
        assert r.apply(block("「殺す」")).modified is False

    def test_custom_pools(self):
        r = ThreatSubtextRule(cold_phrases=["P"], threat_actions=["A"])
        out = r.apply(block("「潰してやる」"))
        assert "P" in out.block.lines[0] and "A" in out.block.lines[0]

    def test_final_flag(self):
        assert ThreatSubtextRule().final is True


class TestComplianceSubvertRule:
    def test_compliance(self):
        r = ComplianceSubvertRule()
        out = r.apply(block("「はい」"))
        assert out.modified is True

    def test_no_compliance(self):
        r = ComplianceSubvertRule()
        assert r.apply(block("「違う」")).modified is False

    def test_disabled(self):
        r = ComplianceSubvertRule()
        r.enabled = False
        assert r.apply(block("「わかりました」")).modified is False

    def test_silent_branch(self):
        # 決定的シードで 0.6 以上を引くターンを選ぶ
        r = ComplianceSubvertRule()
        for turn in range(20):
            out = r.apply(block("「承知しました」"), SubtextContext(turn_index=turn))
            if out.block.lines[0].startswith("（"):
                assert "無言" in out.block.lines[0]
                return
        pytest.fail("silent branch never reached")


class TestAddressDistanceRule:
    def test_enemy_uses_cold(self):
        r = AddressDistanceRule()
        out = r.apply(block("君 Conciliation".replace(" Conciliation", "、行くぞ")), SubtextContext(relationship="enemy"))
        assert "貴方" in out.block.lines[0]

    def test_former_ally_uses_cold(self):
        r = AddressDistanceRule()
        out = r.apply(block("君、行くぞ"), SubtextContext(relationship="former_ally"))
        assert "貴方" in out.block.lines[0]

    def test_superior_uses_blunt(self):
        r = AddressDistanceRule()
        out = r.apply(block("君、行くぞ"), SubtextContext(power_dynamic="superior"))
        assert "お前" in out.block.lines[0]

    def test_default_keeps_kimi(self):
        r = AddressDistanceRule()
        out = r.apply(block("君、行くぞ"))
        assert out.modified is False

    def test_no_address(self):
        r = AddressDistanceRule()
        assert r.apply(block("何もない")).modified is False

    def test_disabled(self):
        r = AddressDistanceRule()
        r.enabled = False
        assert r.apply(block("君、行くぞ"), SubtextContext(relationship="enemy")).modified is False


class TestExtensionRule:
    def test_applies(self):
        r = ExtensionRule("x", "X", r"foo", "bar")
        out = r.apply(block("a foo b"))
        assert out.modified is True
        assert out.block.lines == ["a bar b"]
        assert "extension rule x" in out.diff_summary

    def test_no_match(self):
        r = ExtensionRule("x", "X", r"foo", "bar")
        assert r.apply(block("nothing")).modified is False

    def test_disabled(self):
        r = ExtensionRule("x", "X", r"foo", "bar")
        r.enabled = False
        assert r.apply(block("foo")).modified is False

    def test_default_tags(self):
        r = ExtensionRule("x", "X", r"foo", "bar")
        assert r.tags == ["extension"]

    def test_create_extension_rules(self):
        rules = create_extension_rules()
        assert len(rules) == 8
        ids = [r.id for r in rules]
        assert ids[0] == "rule_08_apology_deflection"
        assert ids[-1] == "rule_15_unspoken_tension"
        assert all(isinstance(r, ExtensionRule) for r in rules)

    @pytest.mark.parametrize("line", [
        "「ごめんなさい」",
        "「あっ、あっ」",
        "「ここだけの話だけど」",
        "「どうしてそんなことを聞くの？」",
        "「ご親切にどうも」",
        "「見ないでよ！」",
        "「独り言よ」",
        "「言いたいことはそれだけか？」",
    ])
    def test_each_extension_matches(self, line):
        rules = create_extension_rules()
        matched = [r for r in rules if r.apply(block(line)).modified]
        assert matched, line


class TestRuleBase:
    def test_abstract(self):
        with pytest.raises(TypeError):
            RuleBase("x")  # type: ignore[abstract]

    def test_to_model_defaults(self):
        class Dummy(RuleBase):
            def apply(self, block, context=None):
                return None

        d = Dummy("id1")
        m = d.to_model()
        assert m.name == "id1" and m.pattern == "" and m.replacement == ""
        assert m.tags == []
