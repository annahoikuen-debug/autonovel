"""Unit tests for src/narrative/subtext_templates/matcher.py (ContextMatcher)."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.narrative.subtext_templates.matcher import ContextMatcher
from src.narrative.subtext_templates.models import TemplateCandidate, TemplateMetadata
from src.narrative.subtext_engine.models import SubtextContext
from src.narrative.subtext_templates.constraints import CharacterConstraints


class TestContextMatcher:
    @pytest.fixture
    def constraints(self):
        """Mock character constraints that allow all templates."""
        constraints = MagicMock(spec=CharacterConstraints)
        constraints.is_template_allowed.return_value = True
        return constraints

    @pytest.fixture
    def matcher(self, constraints):
        # Use non-existent config path to use empty weights
        return ContextMatcher(scene_config_path="/nonexistent/path", constraints=constraints)

    @pytest.fixture
    def sample_context(self):
        return SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="anger",
            power_dynamic="equal",
            relationship="rival",
            intensity="high",
            genre="fantasy",
            tone="dark",
            history_summary=[],
        )

    @pytest.fixture
    def sample_candidate(self):
        meta = TemplateMetadata(
            id="test_template_001",
            category="emotional",
            weight=1.0,
            final=False,
            context={"emotion": "anger", "power_dynamic": "equal", "relationship": "rival"},
            tags=[],
        )
        return TemplateCandidate(
            id="test_template_001",
            content="Test template content",
            metadata=meta,
        )

    def test_score_candidate_emotion_match(self, matcher, sample_context, sample_candidate):
        # sample_candidate has emotion="anger", power_dynamic="equal", relationship="rival"
        # sample_context has emotion="anger" (match: 1.5x), power_dynamic="equal" (match: 1.3x), relationship="rival" (match: 1.3x)
        # base 1.0 * 1.5 * 1.3 * 1.3 = 2.535
        score = matcher.score_candidate(sample_candidate, sample_context)
        assert score == pytest.approx(2.535, rel=0.01)

    def test_score_candidate_emotion_mismatch(self, matcher, sample_candidate):
        context = SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="joy",
            power_dynamic="equal",
            relationship="rival",
            intensity="high",
            genre="fantasy",
            tone="dark",
            history_summary=[],
        )
        candidate = sample_candidate
        candidate.metadata.context = {"emotion": "anger", "power_dynamic": "equal", "relationship": "rival"}

        score = matcher.score_candidate(candidate, context)
        assert score == 0.0  # emotion mismatch

    def test_score_candidate_emotion_neutral(self, matcher, sample_candidate):
        context = SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="neutral",
            power_dynamic="equal",
            relationship="rival",
            intensity="high",
            genre="fantasy",
            tone="dark",
            history_summary=[],
        )
        candidate = sample_candidate
        candidate.metadata.context = {"emotion": "anger", "power_dynamic": "equal", "relationship": "rival"}

        score = matcher.score_candidate(candidate, context)
        # neutral emotion should not disqualify
        assert score > 0

    def test_score_candidate_power_dynamic_match(self, matcher, sample_context):
        # Create candidate with only power_dynamic context
        meta = TemplateMetadata(
            id="test_template_001",
            category="emotional",
            weight=1.0,
            final=False,
            context={"power_dynamic": "equal"},
            tags=[],
        )
        candidate = TemplateCandidate(
            id="test_template_001",
            content="Test template content",
            metadata=meta,
        )
        context = SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="neutral",
            power_dynamic="equal",
            relationship="rival",
            intensity="high",
            genre="fantasy",
            tone="dark",
            history_summary=[],
        )

        score = matcher.score_candidate(candidate, context)
        # base 1.0 * 1.3 (power_dynamic match) = 1.3
        assert score == pytest.approx(1.3, rel=0.01)

    def test_score_candidate_relationship_match(self, matcher, sample_context):
        meta = TemplateMetadata(
            id="test_template_001",
            category="emotional",
            weight=1.0,
            final=False,
            context={"relationship": "rival"},
            tags=[],
        )
        candidate = TemplateCandidate(
            id="test_template_001",
            content="Test template content",
            metadata=meta,
        )
        context = SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="neutral",
            power_dynamic="equal",
            relationship="rival",
            intensity="high",
            genre="fantasy",
            tone="dark",
            history_summary=[],
        )

        score = matcher.score_candidate(candidate, context)
        # base 1.0 * 1.3 (relationship match) = 1.3
        assert score == pytest.approx(1.3, rel=0.01)

    def test_score_candidate_intensity_match(self, matcher, sample_context):
        meta = TemplateMetadata(
            id="test_template_001",
            category="emotional",
            weight=1.0,
            final=False,
            context={"intensity": "high"},
            tags=[],
        )
        candidate = TemplateCandidate(
            id="test_template_001",
            content="Test template content",
            metadata=meta,
        )
        context = SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="neutral",
            power_dynamic="equal",
            relationship="rival",
            intensity="high",
            genre="fantasy",
            tone="dark",
            history_summary=[],
        )

        score = matcher.score_candidate(candidate, context)
        # base 1.0 * 1.2 (intensity match) = 1.2
        assert score == pytest.approx(1.2, rel=0.01)

    def test_score_candidate_genre_weight(self, matcher):
        meta = TemplateMetadata(
            id="test_template_001",
            category="emotional",
            weight=1.0,
            final=False,
            context={},
            tags=[],
        )
        candidate = TemplateCandidate(
            id="test_template_001",
            content="Test template content",
            metadata=meta,
        )
        context = SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="neutral",
            power_dynamic="equal",
            relationship="rival",
            intensity="high",
            genre="fantasy",
            tone="dark",
            history_summary=[],
        )
        matcher.genre_weights = {"fantasy": {"emotional": 2.0}}

        score = matcher.score_candidate(candidate, context)
        # base 1.0 * genre_weight(2.0) = 2.0
        assert score == pytest.approx(2.0, rel=0.01)

    def test_score_candidate_tone_weight(self, matcher):
        meta = TemplateMetadata(
            id="test_template_001",
            category="emotional",
            weight=1.0,
            final=False,
            context={},
            tags=[],
        )
        candidate = TemplateCandidate(
            id="test_template_001",
            content="Test template content",
            metadata=meta,
        )
        context = SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="neutral",
            power_dynamic="equal",
            relationship="rival",
            intensity="high",
            genre="fantasy",
            tone="dark",
            history_summary=[],
        )
        matcher.tone_weights = {"dark": {"emotional": 1.5}}

        score = matcher.score_candidate(candidate, context)
        # base 1.0 * tone(1.5) = 1.5
        assert score == pytest.approx(1.5, rel=0.01)

    def test_score_candidate_history_penalty(self, matcher):
        meta = TemplateMetadata(
            id="test_template_001",
            category="emotional",
            weight=1.0,
            final=False,
            context={},
            tags=[],
        )
        candidate = TemplateCandidate(
            id="test_template_001",
            content="Test template content",
            metadata=meta,
        )
        context = SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="anger",
            power_dynamic="equal",
            relationship="rival",
            intensity="high",
            genre="fantasy",
            tone="dark",
            history_summary=["test_template_001", "other_001", "other_002"],
        )

        score = matcher.score_candidate(candidate, context)
        # base 1.0 * history_penalty(0.2) = 0.2
        assert score == pytest.approx(0.2, rel=0.01)

    def test_match_filters_by_constraints(self, matcher):
        constraints = MagicMock()
        constraints.is_template_allowed.return_value = False

        matcher_with_constraints = ContextMatcher(scene_config_path="/nonexistent/path", constraints=constraints)
        candidate = MagicMock()
        candidate.metadata = MagicMock()
        candidate.metadata.tags = ["forbidden"]
        candidate.metadata.context = {}
        candidate.metadata.category = "test"
        candidate.metadata.weight = 1.0
        candidate.metadata.final = False
        candidate.metadata.tags = ["forbidden"]
        candidate.metadata.id = "test"
        candidate.model_copy.return_value = candidate

        context = SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="anger",
            power_dynamic="equal",
            relationship="rival",
            intensity="high",
            genre="fantasy",
            tone="dark",
            history_summary=[],
        )

        matches = matcher_with_constraints.match([candidate], context)
        assert len(matches) == 0  # filtered out by constraints

    def test_match_returns_scored_candidates(self, matcher, sample_context):
        # Create a candidate with all context matching sample_context
        meta = TemplateMetadata(
            id="test_template_001",
            category="emotional",
            weight=1.0,
            final=False,
            context={"emotion": "anger", "power_dynamic": "equal", "relationship": "rival"},
            tags=[],
        )
        candidate = TemplateCandidate(
            id="test_template_001",
            content="Test template content",
            metadata=meta,
        )

        matches = matcher.match([candidate], sample_context)
        assert len(matches) == 1
        # emotion match (1.5) * power_dynamic match (1.3) * relationship (1.3) = 2.535
        assert matches[0].score == pytest.approx(2.535, rel=0.01)

    def test_match_sorts_final_first_then_score(self, matcher, sample_context):
        candidate1 = MagicMock()
        candidate1.metadata = MagicMock()
        candidate1.metadata.id = "t1"
        candidate1.metadata.context = {}
        candidate1.metadata.category = "test"
        candidate1.metadata.weight = 1.0
        candidate1.metadata.final = True
        candidate1.metadata.tags = []
        candidate1.model_copy.return_value = candidate1

        candidate2 = MagicMock()
        candidate2.metadata = MagicMock()
        candidate2.metadata.id = "t2"
        candidate2.metadata.context = {}
        candidate2.metadata.category = "test"
        candidate2.metadata.weight = 1.0
        candidate2.metadata.final = False
        candidate2.metadata.tags = []
        candidate2.model_copy.return_value = candidate2

        matches = matcher.match([candidate1, candidate2], sample_context)
        assert matches[0].metadata.final is True
        assert matches[0].metadata.id == "t1"

    def test_select_returns_final_candidate(self, matcher, sample_context):
        candidate = MagicMock()
        candidate.metadata = MagicMock()
        candidate.metadata.final = True
        candidate.metadata.id = "final_001"
        candidate.metadata.context = {}
        candidate.metadata.category = "test"
        candidate.metadata.weight = 1.0
        candidate.metadata.final = True
        candidate.metadata.tags = []
        candidate.model_copy.return_value = candidate

        selected = matcher.select([candidate], sample_context)
        assert selected.metadata.final is True

    def test_select_uses_seeded_randomness(self, matcher):
        candidate1 = MagicMock()
        candidate1.metadata = MagicMock()
        candidate1.metadata.final = False
        candidate1.metadata.id = "t1"
        candidate1.metadata.context = {}
        candidate1.metadata.category = "test"
        candidate1.metadata.weight = 1.0
        candidate1.metadata.final = False
        candidate1.metadata.tags = []
        candidate1.model_copy.return_value = candidate1

        candidate2 = MagicMock()
        candidate2.metadata = MagicMock()
        candidate2.metadata.final = False
        candidate2.metadata.id = "t2"
        candidate2.metadata.context = {}
        candidate2.metadata.category = "test"
        candidate2.metadata.weight = 1.0
        candidate2.metadata.final = False
        candidate2.metadata.tags = []
        candidate2.model_copy.return_value = candidate2

        context = SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="neutral",
            power_dynamic="equal",
            relationship="rival",
            intensity="high",
            genre="fantasy",
            tone="dark",
            history_summary=[],
        )

        # Same seed should produce same result
        sel1 = matcher.select([candidate1, candidate2], context, seed=42)
        sel2 = matcher.select([candidate1, candidate2], context, seed=42)
        assert sel1.metadata.id == sel2.metadata.id

    def test_load_scene_weights_file_not_found(self):
        matcher = ContextMatcher(scene_config_path="/nonexistent/path.yaml")
        assert matcher.genre_weights == {}
        assert matcher.tone_weights == {}

    def test_score_candidate_no_context_fields(self, matcher):
        candidate = MagicMock()
        candidate.metadata = MagicMock()
        candidate.metadata.id = "test"
        candidate.metadata.context = {}
        candidate.metadata.category = "test"
        candidate.metadata.weight = 1.0
        candidate.metadata.final = False
        candidate.metadata.tags = []
        candidate.metadata.id = "test"

        context = SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="",
            power_dynamic="",
            relationship="",
            intensity="",
            genre="fantasy",
            tone="dark",
            history_summary=[],
        )

        score = matcher.score_candidate(candidate, context)
        assert score == 1.0  # base weight only

    def test_fallback_matches_only_allowed_candidates(self, matcher):
        constraints = MagicMock()
        constraints.is_template_allowed.return_value = True

        matcher_no_constraints = ContextMatcher(scene_config_path="/nonexistent/path", constraints=constraints)

        # Candidate with incompatible emotion - should be filtered out in fallback
        candidate_bad = MagicMock()
        candidate_bad.metadata = MagicMock()
        candidate_bad.metadata.id = "bad"
        candidate_bad.metadata.context = {"emotion": "anger"}
        candidate_bad.metadata.tags = []
        candidate_bad.metadata.final = False
        candidate_bad.metadata.category = "test"
        candidate_bad.metadata.weight = 1.0
        candidate_bad.metadata.tags = []
        candidate_bad.model_copy.return_value = candidate_bad

        candidate_good = MagicMock()
        candidate_good.metadata = MagicMock()
        candidate_good.metadata.id = "good"
        candidate_good.metadata.context = {"emotion": "joy"}
        candidate_good.metadata.tags = []
        candidate_good.metadata.final = False
        candidate_good.metadata.category = "test"
        candidate_good.metadata.weight = 1.0
        candidate_good.metadata.tags = []
        candidate_good.model_copy.return_value = candidate_good

        context = SubtextContext(
            scene_id="scene_001",
            turn_index=1,
            speaker="protagonist",
            emotion="joy",
            power_dynamic="equal",
            relationship="rival",
            intensity="high",
            genre="fantasy",
            tone="dark",
            history_summary=[],
        )

        # Test with all constraints passing
        matches = matcher_no_constraints.match([candidate_bad, candidate_good], context)
        # bad should be filtered out by emotion mismatch (0 score)
        assert len(matches) == 1
        assert matches[0].metadata.id == "good"
