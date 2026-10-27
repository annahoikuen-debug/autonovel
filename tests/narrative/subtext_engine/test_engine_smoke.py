"""
Smoke test for SubtextEngine imports and initialization (Step 1).
"""

from src.narrative.subtext_engine import (
    SubtextEngine,
)


def test_smoke_initialization():
    engine = SubtextEngine.create_default()
    assert engine is not None
    assert engine.registry is not None
    rules = engine.registry.list_rules()
    assert len(rules) >= 7
