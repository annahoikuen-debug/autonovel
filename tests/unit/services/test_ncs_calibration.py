"""src/services/ncs_calibration.py (NarrativeCoherenceScorer) の単体テスト."""

from __future__ import annotations

from src.services.ncs_calibration import NarrativeCoherenceScorer


class TestNarrativeCoherenceScorer:
    """NarrativeCoherenceScorer のテスト."""

    def test_calculate_ncs_weighted_average(self):
        scorer = NarrativeCoherenceScorer()
        # plot: 0.4 * 1.0 + char: 0.3 * 1.0 + theme: 0.3 * 1.0 = 1.0
        assert scorer.calculate_ncs(1.0, 1.0, 1.0) == 1.0
        # plot: 0.4 * 0.0 + char: 0.3 * 0.0 + theme: 0.3 * 0.0 = 0.0
        assert scorer.calculate_ncs(0.0, 0.0, 0.0) == 0.0
        # plot: 0.4 * 0.5 + char: 0.3 * 0.5 + theme: 0.3 * 0.5 = 0.5
        assert scorer.calculate_ncs(0.5, 0.5, 0.5) == 0.5
        # plot: 0.4 * 1.0 + char: 0.3 * 0.0 + theme: 0.3 * 0.0 = 0.4
        assert scorer.calculate_ncs(1.0, 0.0, 0.0) == 0.4
        # plot: 0.4 * 0.0 + char: 0.3 * 1.0 + theme: 0.3 * 0.0 = 0.3
        assert scorer.calculate_ncs(0.0, 1.0, 0.0) == 0.3
        # plot: 0.4 * 0.0 + char: 0.3 * 0.0 + theme: 0.3 * 1.0 = 0.3
        assert scorer.calculate_ncs(0.0, 0.0, 1.0) == 0.3

    def test_calculate_ncs_float_values(self):
        scorer = NarrativeCoherenceScorer()
        result = scorer.calculate_ncs(0.8, 0.6, 0.4)
        expected = 0.4 * 0.8 + 0.3 * 0.6 + 0.3 * 0.4
        assert result == expected

    def test_weights_sum_to_one(self):
        scorer = NarrativeCoherenceScorer()
        total = sum(scorer.weights.values())
        assert total == 1.0

    def test_calibrate_diversity_threshold_empty(self):
        scorer = NarrativeCoherenceScorer()
        result = scorer.calibrate_diversity_threshold([])
        assert result == {"threshold_pass": 0.5, "threshold_warn": 0.3}

    def test_calibrate_diversity_threshold_good_only(self):
        scorer = NarrativeCoherenceScorer()
        data = [
            {"score": 0.7, "rating": 5},
            {"score": 0.8, "rating": 4},
            {"score": 0.9, "rating": 5},
        ]
        result = scorer.calibrate_diversity_threshold(data)
        # good_only: threshold_pass = min(good_scores) = 0.7
        # threshold_warn = 0.7 * 0.6 = 0.42
        assert result["threshold_pass"] == 0.7
        assert result["threshold_warn"] == 0.42

    def test_calibrate_diversity_threshold_bad_only(self):
        scorer = NarrativeCoherenceScorer()
        data = [
            {"score": 0.1, "rating": 1},
            {"score": 0.2, "rating": 2},
            {"score": 0.3, "rating": 3},
        ]
        result = scorer.calibrate_diversity_threshold(data)
        # bad_only: threshold_pass = 0.5, threshold_warn = 0.3
        assert result == {"threshold_pass": 0.5, "threshold_warn": 0.3}

    def test_calibrate_diversity_threshold_mixed(self):
        scorer = NarrativeCoherenceScorer()
        data = [
            {"score": 0.9, "rating": 5},  # good
            {"score": 0.8, "rating": 4},  # good
            {"score": 0.3, "rating": 2},  # bad
            {"score": 0.2, "rating": 1},  # bad
        ]
        result = scorer.calibrate_diversity_threshold(data)
        # good_scores = [0.9, 0.8], bad_scores = [0.3, 0.2]
        # max(good) = 0.9, min(bad) = 0.2
        # threshold_pass = (0.9 + 0.2) / 2 = 0.55
        # threshold_warn = 0.55 * 0.6 = 0.33
        assert result["threshold_pass"] == 0.55
        assert result["threshold_warn"] == 0.33

    def test_calibrate_diversity_threshold_rating_missing(self):
        scorer = NarrativeCoherenceScorer()
        # rating キーがない場合は d.get("rating", 0) = 0 < 4 なので bad
        data = [
            {"score": 0.9},  # bad (rating 0)
            {"score": 0.8, "rating": 5},  # good
        ]
        result = scorer.calibrate_diversity_threshold(data)
        # good_scores = [0.8], bad_scores = [0.9]
        # max(good) = 0.8, min(bad) = 0.9
        # threshold_pass = (0.8 + 0.9) / 2 = 0.85
        # threshold_warn = 0.85 * 0.6 = 0.51
        assert abs(result["threshold_pass"] - 0.85) < 1e-9
        assert abs(result["threshold_warn"] - 0.51) < 1e-9
