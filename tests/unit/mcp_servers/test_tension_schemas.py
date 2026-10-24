"""Unit tests for tension schemas."""

from __future__ import annotations

from src.mcp_servers.tension_schemas import TensionScore, TENSION_KEYWORDS


def test_tension_schemas_instantiation():
    score = TensionScore(
        tension_score=85.0, polarity=-0.5, dominant_emotion="tension", feedback="High tension detected."
    )
    assert score.tension_score == 85.0
    assert score.polarity == -0.5
    assert len(TENSION_KEYWORDS["high_tension"]) > 0
