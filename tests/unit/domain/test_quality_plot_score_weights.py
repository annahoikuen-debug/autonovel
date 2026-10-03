"""`calculate_plot_quality_score` の重みキーの回帰テスト。

このテストが固定する問題
----------------------
``QualityCalculator.PLOT_QUALITY_DIMENSIONS`` のキー
（``state_integrity`` / ``emotional_resonance`` / ``thematic_depth`` /
``literary_beauty`` / ``erotic_intensity``）と
``BookScore.WEIGHTS`` のキー（``story`` / ``character`` / ... ）は
**1 つも重複していない**。

``calculate_plot_quality_score`` が ``weights`` 省略時に
``BookScore.WEIGHTS`` を使っていたため、``calculate_from_dimensions`` の
``total_weight`` が 0 になり、**全プロットの品質スコアが常に 0** になっていた
（= 品質ゲートが機能していない）。 Plot 軸専用の重み
（``BookScore.PLOT_QUALITY_WEIGHTS``）を使うことで修正済み。

本テストは「全次元が 70 なら総合も 70」という自明な性質を固定し、
重みが 1 つも一致していない場合（= 0 点）が再発しないようにする。
"""

from __future__ import annotations

from src.domain.domain_services.quality_domain_service import QualityCalculator
from src.domain.value_objects.scores import BookScore


class _FakePlot:
    """``PLOT_QUALITY_DIMENSIONS`` が参照する属性だけを持つスタブ。"""

    def __init__(self, value: int) -> None:
        self.state_integrity_score = value
        self.emotional_resonance_score = value
        self.thematic_depth_score = value
        self.literary_beauty_score = value
        self.erotic_intensity = value


def test_plot_quality_score_is_not_zero_for_uniform_dimensions():
    """全次元 70 なら総合スコアも 70（0 にならない）。"""
    score = QualityCalculator.calculate_plot_quality_score(_FakePlot(70))

    assert score.overall == 70, (
        "plot 品質スコアが 0 になった（重みキーの不一致で total_weight=0）"
    )


def test_plot_quality_dimension_keys_have_matching_weights():
    """plot 次元キーに対応する重みが必ず存在する（重みの脱落を防止）。"""
    weights = QualityCalculator.PLOT_QUALITY_WEIGHTS
    for dim in QualityCalculator.PLOT_QUALITY_DIMENSIONS:
        assert dim in weights, f"plot 次元 {dim!r} に対応する重みがない"


def test_plot_quality_weights_are_disjoint_from_book_weights():
    """plot 軸と book 軸の重みは別々。

    つまり plot 集計に ``BookScore.WEIGHTS`` を流用してはいけない
    （流用すると total_weight=0 になり常に 0 点になる）。
    """
    assert not (set(BookScore.WEIGHTS) & set(BookScore.PLOT_QUALITY_WEIGHTS))
    assert QualityCalculator.PLOT_QUALITY_WEIGHTS == BookScore.PLOT_QUALITY_WEIGHTS


def test_plot_quality_score_scales_with_dimensions():
    """次元値を上げれば総合スコアも上がる（常に 0 でないことの追加確認）。"""
    low = QualityCalculator.calculate_plot_quality_score(_FakePlot(20))
    high = QualityCalculator.calculate_plot_quality_score(_FakePlot(90))

    assert low.overall == 20
    assert high.overall == 90
