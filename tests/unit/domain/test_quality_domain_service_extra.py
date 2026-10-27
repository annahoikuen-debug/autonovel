"""QualityDomainService の追加単体テスト（計算・アナライズ部分）."""

from types import SimpleNamespace

import pytest

from src.domain.domain_services.quality_domain_service import (
    QualityAnalyzer,
    QualityCalculator,
    QualityDomainService,
    QualityGrade,
    QualityThresholds,
    QualityValidationError,
    QualityValidator,
)
from src.domain.value_objects.ids import NovelId
from src.domain.value_objects.scores import BookScore, CostScore, QolScore, TensionScore


class FakePlot:
    def __init__(self, episode_number=1, tension=50, catharsis=0, catharsis_type="",
                 state_integrity=100, emotional_resonance=0, thematic_depth=0,
                 literary_beauty=0, erotic_intensity=0, cost_score=0.0, qol_delta=0):
        self.episode_number = episode_number
        self.tension_score = TensionScore(value=tension)
        self.catharsis = catharsis
        self.catharsis_type = catharsis_type
        self.state_integrity_score = state_integrity
        self.emotional_resonance_score = emotional_resonance
        self.thematic_depth_score = thematic_depth
        self.literary_beauty_score = literary_beauty
        self.erotic_intensity = erotic_intensity
        self.cost_score = cost_score
        self.qol_delta = qol_delta


class FakeChapter:
    def __init__(self, score_story=None):
        self.score_story = score_story


class TestValidator:
    def test_validate_dimension_score_ok(self):
        assert QualityValidator.validate_dimension_score(50, "story") == []

    def test_validate_dimension_score_range(self):
        errs = QualityValidator.validate_dimension_score(150, "story")
        assert len(errs) == 1
        assert "story" in errs[0]

    def test_validate_book_score(self):
        bs = BookScore(overall=80, dimensions={"story": 70})
        assert QualityValidator.validate_book_score(bs) == []

    def test_validate_tension_score(self):
        assert QualityValidator.validate_tension_score(TensionScore(value=30)) == []

    def test_validate_qol_score(self):
        assert QualityValidator.validate_qol_score(QolScore(value=30, factors={"a": 20})) == []

    def test_validate_cost_score(self):
        assert QualityValidator.validate_cost_score(CostScore(value=1.0, tokens_used=10)) == []

    def test_thresholds(self):
        assert QualityThresholds.PASSING_SCORE == 60
        assert QualityThresholds.CRITICAL_ISSUE_DEDUCTION == 30

    def test_validate_book_score_out_of_range(self):
        # 正値オブジェクトは構築時に弾かれるため、構造的に同じスタブを渡す
        stub = SimpleNamespace(overall=150, dimensions={"story": 90, "prose": 120})
        errs = QualityValidator.validate_book_score(stub)
        assert len(errs) == 2

    def test_validate_tension_score_out_of_range(self):
        errs = QualityValidator.validate_tension_score(SimpleNamespace(value=120))
        assert errs == ["Tension value must be between 0 and 100, got 120"]

    def test_validate_qol_score_out_of_range(self):
        errs = QualityValidator.validate_qol_score(SimpleNamespace(value=120, factors={"a": 5, "b": 200}))
        assert len(errs) == 2

    def test_validate_cost_score_out_of_range(self):
        errs = QualityValidator.validate_cost_score(SimpleNamespace(value=-1.0, tokens_used=-5))
        assert len(errs) == 2


class TestCalculator:
    def test_calculate_book_score(self):
        bs = QualityCalculator.calculate_book_score({"story": 100, "prose": 50})
        assert isinstance(bs, BookScore)
        assert 0 <= bs.overall <= 100

    def test_calculate_book_score_empty(self):
        assert QualityCalculator.calculate_book_score({}).overall == 0

    def test_calculate_plot_quality_score(self):
        plot = FakePlot(state_integrity=100, emotional_resonance=100, thematic_depth=100)
        bs = QualityCalculator.calculate_plot_quality_score(plot)
        assert "state_integrity" in bs.dimensions

    def test_calculate_plot_quality_score_clamps(self):
        plot = FakePlot(state_integrity=1000, emotional_resonance=-50)
        bs = QualityCalculator.calculate_plot_quality_score(plot)
        assert bs.dimensions["state_integrity"] == 100
        assert bs.dimensions["emotional_resonance"] == 0

    def test_calculate_plot_quality_score_missing_attrs(self):
        plot = SimpleNamespace()
        assert QualityCalculator.calculate_plot_quality_score(plot).overall == 0

    def test_calculate_chapter_quality_score(self):
        bs = QualityCalculator.calculate_chapter_quality_score(FakeChapter(score_story=80))
        assert bs.dimensions["story"] == 80

    def test_calculate_chapter_quality_score_none(self):
        assert QualityCalculator.calculate_chapter_quality_score(FakeChapter()) is None

    def test_calculate_aggregate_quality(self):
        plot_bs = QualityCalculator.calculate_book_score({"story": 100})
        chap_bs = QualityCalculator.calculate_book_score({"story": 50})
        agg = QualityCalculator.calculate_aggregate_quality([plot_bs], [chap_bs, None])
        assert agg.dimensions["story"] == 75

    def test_calculate_aggregate_quality_empty(self):
        assert QualityCalculator.calculate_aggregate_quality([], []).overall == 0

    def test_tension_curve_empty(self):
        assert QualityCalculator.calculate_tension_curve([]) == {
            "episodes": [], "trend": "unknown", "peaks": [], "valleys": []
        }

    def test_tension_curve_peaks_valleys(self):
        plots = [
            FakePlot(1, tension=10),
            FakePlot(2, tension=80),
            FakePlot(3, tension=20),
            FakePlot(4, tension=70),
        ]
        curve = QualityCalculator.calculate_tension_curve(plots)
        assert curve["peaks"][0]["episode"] == 2
        assert curve["trend"] == "rising"
        assert curve["max_tension"] == 80
        assert curve["min_tension"] == 10

    def test_tension_curve_valley(self):
        plots = [FakePlot(1, tension=80), FakePlot(2, tension=10), FakePlot(3, tension=80)]
        assert QualityCalculator.calculate_tension_curve(plots)["valleys"][0]["episode"] == 2

    def test_tension_curve_falling(self):
        plots = [FakePlot(1, tension=90), FakePlot(2, tension=20)]
        assert QualityCalculator.calculate_tension_curve(plots)["trend"] == "falling"

    def test_tension_curve_stable(self):
        plots = [FakePlot(1, tension=50), FakePlot(2, tension=55)]
        assert QualityCalculator.calculate_tension_curve(plots)["trend"] == "stable"

    def test_tension_curve_sorted(self):
        plots = [FakePlot(2, tension=30), FakePlot(1, tension=20)]
        assert [e for e, _ in QualityCalculator.calculate_tension_curve(plots)["episodes"]] == [1, 2]

    def test_catharsis_distribution_empty(self):
        assert QualityCalculator.calculate_catharsis_distribution([])["total"] == 0

    def test_catharsis_distribution(self):
        plots = [FakePlot(1, catharsis=85, catharsis_type="revenge"), FakePlot(2, catharsis=10)]
        dist = QualityCalculator.calculate_catharsis_distribution(plots)
        assert dist["total"] == 2
        assert dist["catharsis_episodes"][0]["type"] == "revenge"
        assert dist["catharsis_rate"] == 50.0

    def test_cost_efficiency_empty(self):
        assert QualityCalculator.calculate_cost_efficiency([])["efficiency_score"] == 100

    def test_cost_efficiency(self):
        plots = [FakePlot(1, cost_score=2.0, qol_delta=5), FakePlot(2, cost_score=1.0, qol_delta=5)]
        res = QualityCalculator.calculate_cost_efficiency(plots)
        assert res["total_cost"] == 3.0
        assert res["total_tokens"] == 10
        assert res["avg_cost_per_episode"] == 1.5
        assert res["efficiency_score"] == 70

    def test_qol_score_empty(self):
        assert QualityCalculator.calculate_qol_score([]).value == 50

    def test_qol_score(self):
        plots = [FakePlot(1, qol_delta=10), FakePlot(2, qol_delta=-10)]
        qol = QualityCalculator.calculate_qol_score(plots)
        assert qol.value == 50
        assert qol.factors["episode_1"] == 60
        assert qol.factors["episode_2"] == 40

    def test_qol_score_no_deltas(self):
        assert QualityCalculator.calculate_qol_score([FakePlot(1, qol_delta=0)]).value == 50

    def test_qol_score_clamps(self):
        qol = QualityCalculator.calculate_qol_score([FakePlot(1, qol_delta=200)])
        assert qol.factors["episode_1"] == 100

    def test_get_quality_grade(self):
        assert QualityCalculator.get_quality_grade(95) == QualityGrade.S
        assert QualityCalculator.get_quality_grade(80) == QualityGrade.A
        assert QualityCalculator.get_quality_grade(70) == QualityGrade.B
        assert QualityCalculator.get_quality_grade(60) == QualityGrade.C
        assert QualityCalculator.get_quality_grade(50) == QualityGrade.D
        assert QualityCalculator.get_quality_grade(10) == QualityGrade.F

    def test_quality_trend_insufficient(self):
        assert QualityCalculator.calculate_quality_trend([])["trend"] == "insufficient_data"
        assert QualityCalculator.calculate_quality_trend([BookScore(overall=50)])["change"] == 0

    def test_quality_trend_improving(self):
        res = QualityCalculator.calculate_quality_trend([BookScore(overall=50), BookScore(overall=60)])
        assert res["trend"] == "improving"
        assert res["change"] == 10

    def test_quality_trend_declining(self):
        res = QualityCalculator.calculate_quality_trend([BookScore(overall=60), BookScore(overall=40)])
        assert res["trend"] == "declining"

    def test_quality_trend_stable(self):
        res = QualityCalculator.calculate_quality_trend([BookScore(overall=50), BookScore(overall=52)])
        assert res["trend"] == "stable"

    def test_default_weights_sum(self):
        assert abs(sum(QualityCalculator.DEFAULT_WEIGHTS.values()) - 1.0) < 0.001


class TestAnalyzer:
    def test_identify_weak_and_strong(self):
        bs = BookScore(overall=60, dimensions={"story": 40, "prose": 90})
        assert QualityAnalyzer.identify_weak_dimensions(bs) == ["story"]
        assert QualityAnalyzer.identify_strong_dimensions(bs) == ["prose"]

    def test_dimension_balance_empty(self):
        assert QualityAnalyzer.calculate_dimension_balance(BookScore(overall=50)) == 100.0

    def test_dimension_balance_perfect(self):
        bs = BookScore(overall=70, dimensions={"story": 70, "prose": 70})
        assert QualityAnalyzer.calculate_dimension_balance(bs) == 100.0

    def test_dimension_balance_unbalanced(self):
        bs = BookScore(overall=50, dimensions={"story": 0, "prose": 100})
        assert QualityAnalyzer.calculate_dimension_balance(bs) == 0.0

    def test_generate_quality_report(self):
        bs = BookScore(overall=60, dimensions={"story": 40, "prose": 90})
        report = QualityAnalyzer.generate_quality_report(bs, [bs], [bs, None])
        assert report["grade"] == "C"
        assert report["plot_count"] == 1
        assert report["chapter_count"] == 1
        assert report["recommendations"]

    def test_generate_recommendations_unbalanced(self):
        recs = QualityAnalyzer._generate_recommendations(["story"], 10.0)
        assert any("unbalanced" in r for r in recs)
        assert any("plot structure" in r for r in recs)

    def test_generate_recommendations_unknown_dim(self):
        recs = QualityAnalyzer._generate_recommendations(["mystery"], 90.0)
        assert len(recs) == 1

    def test_generate_recommendations_none(self):
        assert QualityAnalyzer._generate_recommendations([], 90.0) == []


class TestQualityDomainServiceExtra:
    def make(self) -> QualityDomainService:
        return QualityDomainService()

    def test_post_init(self):
        svc = self.make()
        assert isinstance(svc._validator, QualityValidator)
        assert isinstance(svc._calculator, QualityCalculator)
        assert isinstance(svc._analyzer, QualityAnalyzer)

    def test_calculate_plot_quality(self):
        svc = self.make()
        assert isinstance(svc.calculate_plot_quality(FakePlot()), BookScore)

    def test_calculate_chapter_quality(self):
        svc = self.make()
        assert svc.calculate_chapter_quality(FakeChapter()) is None
        assert svc.calculate_chapter_quality(FakeChapter(score_story=70)).overall > 0

    def test_calculate_novel_quality(self):
        svc = self.make()
        assert isinstance(svc.calculate_novel_quality([FakePlot()], [FakeChapter(score_story=70)]), BookScore)

    def test_validate_plot_scores_ok(self):
        svc = self.make()
        assert svc.validate_plot_scores(FakePlot(state_integrity=100, emotional_resonance=50)) == []

    def test_validate_plot_scores_errors(self):
        svc = self.make()
        errors = svc.validate_plot_scores(FakePlot(state_integrity=500, emotional_resonance=20))
        assert any("state_integrity" in e for e in errors)

    def test_validate_chapter_scores(self):
        svc = self.make()
        assert svc.validate_chapter_scores(FakeChapter()) == []
        assert svc.validate_chapter_scores(FakeChapter(score_story=80)) == []

    def test_get_quality_grade(self):
        assert self.make().get_quality_grade(95) == QualityGrade.S

    def test_analyses(self):
        svc = self.make()
        assert svc.analyze_tension_curve([FakePlot()])["total" if False else "trend"] == "stable"
        assert svc.analyze_catharsis_distribution([FakePlot()])["total"] == 1
        assert svc.analyze_cost_efficiency([FakePlot()])["total_cost"] == 0.0
        assert svc.analyze_qol([FakePlot()]).value == 50

    def test_generate_quality_report(self):
        svc = self.make()
        report = svc.generate_quality_report(
            NovelId("novel-1"), [FakePlot()], [FakeChapter(score_story=70)]
        )
        assert report["novel_id"] == str(NovelId("novel-1"))
        assert "generated_at" in report
        assert "tension_analysis" in report
        assert "catharsis_analysis" in report
        assert "cost_analysis" in report
        assert report["qol_analysis"]["value"] == 50

    def test_calculate_quality_trend(self):
        svc = self.make()
        assert svc.calculate_quality_trend([])["trend"] == "insufficient_data"

    def test_get_dimension_weights(self):
        weights = self.make().get_dimension_weights()
        weights["story"] = 0.9
        assert QualityCalculator.DEFAULT_WEIGHTS["story"] == 0.20

    def test_set_custom_weights_affects_only_this_instance(self):
        """カスタム重みはインスタンス単位に効き、クラス属性は汚さない。

        旧挙動では ``QualityCalculator`` に ``__init__`` が無く
        ``self._calculator`` がクラスそのものだったため、``set_custom_weights`` が
        プロセス全体で ``DEFAULT_WEIGHTS`` を書き換えていた。
        """
        before = dict(QualityCalculator.DEFAULT_WEIGHTS)
        svc = self.make()
        other = self.make()

        plot = FakePlot(
            state_integrity=100,
            emotional_resonance=50,
            thematic_depth=0,
            literary_beauty=0,
            erotic_intensity=0,
        )
        svc.set_custom_weights({"state_integrity": 0.5, "emotional_resonance": 0.5})

        # 1) 実際に計算結果に影響する
        assert svc.get_dimension_weights() == {"state_integrity": 0.5, "emotional_resonance": 0.5}
        assert svc.calculate_plot_quality(plot).overall == 75

        # 2) 他のインスタンスに影響しない（既定 PLOT_QUALITY_WEIGHTS のまま）
        assert other.get_dimension_weights() == before
        assert other.calculate_plot_quality(plot).overall == 35

        # 3) クラス属性は変更されない
        assert QualityCalculator.DEFAULT_WEIGHTS == before
        assert QualityCalculator.DEFAULT_WEIGHTS["story"] == 0.20

    def test_custom_weights_change_computed_score(self):
        """story に全重みを与えると story スコアがそのまま総合点になる。"""
        svc = self.make()
        plot = FakePlot(
            state_integrity=100,
            emotional_resonance=0,
            thematic_depth=0,
            literary_beauty=0,
            erotic_intensity=0,
        )
        default_score = svc.calculate_plot_quality(plot)

        svc.set_custom_weights({"state_integrity": 1.0})
        custom_score = svc.calculate_plot_quality(plot)

        assert default_score.overall == 25
        assert custom_score.overall == 100
        assert custom_score.overall != default_score.overall

    def test_calculate_from_dimensions_uses_default_weights(self):
        """weights 未指定時は BookScore.WEIGHTS が使われる。"""
        dims = {"story": 100, "character": 0}
        score = BookScore.calculate_from_dimensions(dims)
        # (100*0.20 + 0*0.15) / 0.35
        assert score.overall == 57
        assert score.dimensions == dims

    def test_calculate_from_dimensions_honours_custom_weights(self):
        """weights 引数が渡されればそれだけで重み付けされる。"""
        dims = {"story": 100, "character": 0}
        assert BookScore.calculate_from_dimensions(dims, {"story": 1.0}).overall == 100
        assert BookScore.calculate_from_dimensions(dims, {"character": 1.0}).overall == 0

    def test_plot_quality_weights_are_disjoint_from_book_weights(self):
        """PLOT_QUALITY_WEIGHTS は BookScore.WEIGHTS とキーが重ならない。

        重なる前に ``calculate_plot_quality_score`` は BookScore.WEIGHTS を流用して
        total_weight=0 になり、常に overall=0 を返していた。
        """
        assert set(BookScore.PLOT_QUALITY_WEIGHTS) == set(
            QualityCalculator.PLOT_QUALITY_DIMENSIONS
        )
        assert not (set(BookScore.PLOT_QUALITY_WEIGHTS) & set(BookScore.WEIGHTS))
        assert set(QualityCalculator.PLOT_QUALITY_WEIGHTS) == set(BookScore.PLOT_QUALITY_WEIGHTS)

    def test_calculate_plot_quality_score_is_not_zero(self):
        """plot の品質軸が全て最大なら PLOT_QUALITY_WEIGHTS で 100 になる。"""
        plot = FakePlot(
            state_integrity=100,
            emotional_resonance=100,
            thematic_depth=100,
            literary_beauty=100,
            erotic_intensity=100,
        )
        assert QualityCalculator.calculate_plot_quality_score(plot).overall == 100
        assert abs(sum(BookScore.PLOT_QUALITY_WEIGHTS.values()) - 1.0) < 1e-9

    def test_calculate_plot_quality_uses_custom_weights(self):
        """インスタンスのカスタム重みが plot 品質計算にも効く。"""
        svc = self.make()
        plot = FakePlot(
            state_integrity=100,
            emotional_resonance=0,
            thematic_depth=0,
            literary_beauty=0,
            erotic_intensity=0,
        )
        svc.set_custom_weights({"state_integrity": 1.0})
        assert svc.calculate_plot_quality(plot).overall == 100

    def test_set_custom_weights_invalid(self):
        svc = self.make()
        with pytest.raises(QualityValidationError):
            svc.set_custom_weights({"story": 0.5})

