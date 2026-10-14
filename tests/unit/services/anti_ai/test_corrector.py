import pytest
from src.services.anti_ai.corrector import _apply_replacements, BaseCorrector, CorrectedText
from src.services.anti_ai.models import AICategory, ViolationSpan

def test_apply_replacements():
    text = "Hello world"
    replacements = [(0, 5, "Hi"), (6, 11, "universe")]
    assert _apply_replacements(text, replacements) == "Hi universe"

    # Test overlap warning
    replacements = [(0, 5, "Hi"), (2, 7, "bad")]
    assert _apply_replacements(text, replacements) == "Hi world" # cursor will skip overlapping

class MockCorrector(BaseCorrector):
    category = AICategory.SAME_STRUCTURE
    def _build_replacements(self, text, violations):
        return [(v.start, v.end, "replaced") for v in violations]

def test_base_corrector():
    corrector = MockCorrector()
    text = "aaa bbb ccc"
    violations = [ViolationSpan(category=AICategory.SAME_STRUCTURE, start=0, end=3, matched_text="aaa")]

    result = corrector.correct(text, violations)
    assert result.text == "replaced bbb ccc"
    assert result.changes == 1
    assert result.skipped == 0

    # Test no violations
    result = corrector.correct(text, [])
    assert result.text == text

    # Test violation category mismatch
    violations = [ViolationSpan(category=AICategory.TRANSITION_OVERUSE, start=0, end=3, matched_text="aaa")]
    result = corrector.correct(text, violations)
    assert result.text == text
    assert result.changes == 0
    assert result.skipped == 0
