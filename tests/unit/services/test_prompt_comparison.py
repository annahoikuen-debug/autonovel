"""src/services/prompt_comparison.py (weighted_total / decide_winner) の単体テスト."""

from __future__ import annotations

from src.services.prompt_comparison import DEFAULT_WEIGHTS, decide_winner, weighted_total


class TestWeightedTotal:
    """weighted_total 関数のテスト."""

    def test_weighted_total_default_weights(self):
        scores = {
            "hook_retention": 1.0,
            "pacing": 1.0,
            "character_consistency": 1.0,
            "commercial_viability": 1.0,
            "emotional_resonance": 1.0,
            "coherence": 1.0,
        }
        result = weighted_total(scores)
        # 全重みの合計 = 1.0、全スコア 1.0 なので total = 1.0
        assert result == 1.0

    def test_weighted_total_zero_scores(self):
        scores = {
            "hook_retention": 0.0,
            "pacing": 0.0,
            "character_consistency": 0.0,
            "commercial_viability": 0.0,
            "emotional_resonance": 0.0,
            "coherence": 0.0,
        }
        result = weighted_total(scores)
        assert result == 0.0

    def test_weighted_total_partial_scores(self):
        scores = {
            "hook_retention": 1.0,
            "pacing": 0.0,
            "character_consistency": 0.0,
            "commercial_viability": 0.0,
            "emotional_resonance": 0.0,
            "coherence": 0.0,
        }
        result = weighted_total(scores)
        # 0.2 * 1.0 + 他は0 = 0.2
        assert result == 0.2

    def test_weighted_total_missing_keys(self):
        scores = {}
        result = weighted_total(scores)
        # スコアがないキーは 0.0 扱い
        assert result == 0.0

    def test_weighted_total_custom_weights(self):
        scores = {"a": 10.0, "b": 20.0}
        weights = {"a": 0.3, "b": 0.7}
        result = weighted_total(scores, weights)
        # 0.3 * 10 + 0.7 * 20 = 3 + 14 = 17
        assert result == 17.0

    def test_weighted_total_rounding(self):
        scores = {"a": 1.0}
        weights = {"a": 0.3333}
        result = weighted_total(scores, weights)
        # 0.3333 * 1.0 = 0.3333, round(..., 4) = 0.3333
        assert result == 0.3333


class TestDecideWinner:
    """decide_winner 関数のテスト."""

    def test_decide_winner_empty(self):
        result = decide_winner([])
        assert result == {"winner_id": None, "reason": "no results"}

    def test_decide_winner_single(self):
        results = [
            {
                "version_id": "v1",
                "label": "バージョン1",
                "weighted_total": 0.5,
            }
        ]
        result = decide_winner(results)
        assert result["winner_id"] == "v1"
        assert result["winner_label"] == "バージョン1"
        assert result["reason"] == "最高合計スコア"

    def test_decide_winner_multiple(self):
        results = [
            {
                "version_id": "v1",
                "label": "バージョン1",
                "weighted_total": 0.5,
            },
            {
                "version_id": "v2",
                "label": "バージョン2",
                "weighted_total": 0.8,
            },
            {
                "version_id": "v3",
                "label": "バージョン3",
                "weighted_total": 0.3,
            },
        ]
        result = decide_winner(results)
        assert result["winner_id"] == "v2"
        assert result["winner_label"] == "バージョン2"

    def test_decide_winner_custom_weights(self):
        results = [
            {
                "version_id": "v1",
                "label": "v1",
                "weighted_total": 0.9,
            },
            {
                "version_id": "v2",
                "label": "v2",
                "weighted_total": 0.8,
            },
        ]
        weights = {"a": 0.5, "b": 0.5}
        result = decide_winner(results, weights)
        assert result["winner_id"] == "v1"

    def test_default_weights_sum_to_one(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert total == 1.0
