"""Branch coverage tests for src/services/book_score_service.py."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.book_score_models import BookScore
from src.services.book_score_service import (
    NEUTRAL_SCORE,
    BookScoreCalculator,
    BookScoreService,
    ScoringUnavailableError,
)


def make_calc(repository=None, bridge=None):
    return BookScoreCalculator(config_path="nonexistent.yaml", repository=repository, bridge=bridge)


def make_result(value):
    """Build a SQLAlchemy-like result returning `value` from scalars()."""
    res = MagicMock()
    scalars = res.scalars.return_value
    if isinstance(value, list):
        scalars.all.return_value = value
        scalars.first.return_value = value[0] if value else None
    else:
        scalars.first.return_value = value
        scalars.all.return_value = [value] if value is not None else []
    return res


def make_repo(plot=None, chapter=None, illustration=None, bible=None, audit=None):
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.get_latest = AsyncMock()
    repo.get_all_for_book = AsyncMock(return_value=[])

    state = {"plot": plot, "chapter": chapter, "illustration": illustration, "bible": bible, "audit": audit}

    # Simpler: dispatch on the table referenced in the compiled statement
    async def _execute(stmt):
        s = str(stmt)
        if "plots" in s:
            return make_result(state["plot"])
        if "chapters" in s:
            return make_result(state["chapter"])
        if "illustrations" in s:
            return make_result(state["illustration"])
        if "bibles" in s:
            return make_result(state["bible"])
        return make_result(state["audit"])

    repo.session = MagicMock()
    repo.session.execute = AsyncMock(side_effect=_execute)
    return repo


def issue(category="", severity="", description=""):
    obj = MagicMock()
    obj.category = category
    obj.severity = severity
    obj.description = description
    return obj


def chapter_obj(content=None, tension=None):
    obj = MagicMock()
    obj.content = content
    obj.tension = tension
    return obj


class TestConstruction:
    def test_alias_is_same_class(self):
        assert BookScoreService is BookScoreCalculator

    def test_missing_config_uses_fallback_weights(self):
        calc = make_calc()
        assert calc.default_weights["structure"] == 25
        assert calc.genre_overrides == {}

    def test_config_loaded_from_yaml(self, tmp_path):
        p = tmp_path / "w.yaml"
        p.write_text(
            "default:\n"
            "  structure: 40\n"
            "genre_overrides:\n"
            "  fantasy:\n"
            "    structure: 60\n"
            "phase_overrides:\n"
            "  draft:\n"
            "    structure: 30\n",
            encoding="utf-8",
        )
        calc = BookScoreCalculator(config_path=str(p))
        assert calc.default_weights["structure"] == 40
        assert calc.genre_overrides["fantasy"]["structure"] == 60
        assert calc.phase_overrides["draft"]["structure"] == 30

    def test_get_weights_applies_overrides(self):
        calc = make_calc()
        calc.default_weights = {"structure": 25}
        calc.genre_overrides = {"fantasy": {"structure": 50}}
        calc.phase_overrides = {"draft": {"structure": 10}}
        assert calc._get_weights("fantasy", "draft")["structure"] == 10
        assert calc._get_weights("unknown", "unknown") == {"structure": 25}
        assert calc._get_weights("", "") == {"structure": 25}

    def test_explicit_bridge_used(self):
        b = object()
        assert make_calc(bridge=b).bridge is b

    def test_lazy_bridge_created(self):
        calc = make_calc()
        calc.bridge = None
        calc.get_score_contributions({"structure": 1.0})
        assert calc.bridge is not None


class TestBridgeDelegation:
    def _u5d(self):
        u = MagicMock()
        u.overall_score = 77.0
        u.structure_score = 70.0
        u.coherency_score = 80.0
        u.factual_grounding_score = 60.0
        u.visual_textual_synergy_score = 90.0
        u.reader_experience_score = 65.0
        u.contributions = {"structure": {"structure_specialist": 10.0}}
        u.to_dict.return_value = {"overall": 77.0}
        return u

    def test_calculate_from_specialists(self):
        bridge = MagicMock()
        bridge.map_to_5d.return_value = self._u5d()
        calc = make_calc(bridge=bridge)
        score = calc.calculate_from_specialists({"structure": 80.0}, genre="fantasy", phase="draft")
        assert isinstance(score, BookScore)
        assert score.overall_score == 77.0
        assert score.specialist_breakdown == {"overall": 77.0}
        bridge.map_to_5d.assert_called_once_with({"structure": 80.0}, genre="fantasy", phase="draft")

    def test_get_score_contributions(self):
        bridge = MagicMock()
        bridge.map_to_5d.return_value = self._u5d()
        calc = make_calc(bridge=bridge)
        assert calc.get_score_contributions({"x": 1.0}) == {"structure": {"structure_specialist": 10.0}}

    def test_dimension_to_specialists_mapping(self):
        bridge = MagicMock()
        bridge.get_matrix_for_genre.return_value = {"structure": {"a": 1.0}}
        calc = make_calc(bridge=bridge)
        assert calc.get_dimension_to_specialists_mapping("fantasy") == {"structure": {"a": 1.0}}

    def test_specialist_to_dimensions_mapping(self):
        bridge = MagicMock()
        bridge.get_matrix_for_genre.return_value = {
            "structure": {"a": 1.0, "b": 2.0},
            "coherency": {"a": 3.0, "c": 4.0},
        }
        calc = make_calc(bridge=bridge)
        rev = calc.get_specialist_to_dimensions_mapping()
        assert rev == {"a": {"structure": 1.0, "coherency": 3.0}, "b": {"structure": 2.0}, "c": {"coherency": 4.0}}


class TestMaturityReport:
    @pytest.mark.parametrize(
        "overall,rank",
        [(90.0, "S"), (80.0, "A"), (70.0, "B"), (55.0, "C"), (10.0, "D")],
    )
    def test_ranks(self, overall, rank):
        calc = make_calc()
        score = BookScore(overall, 50, 50, 50, 50, 50)
        report = calc.generate_maturity_report(score)
        assert report["rank"] == rank
        assert report["overall_score"] == overall
        assert report["is_commercial_ready"] is (overall >= 85.0)
        assert report["is_web_hit_ready"] is (overall >= 75.0)
        assert report["lowest_dimension"] in report["dimensions"]

    def test_assessment_text_present(self):
        calc = make_calc()
        score = BookScore(90.0, 1, 2, 3, 4, 5)
        report = calc.generate_maturity_report(score, genre="fantasy", phase="draft")
        assert "商業出版水準" in report["assessment"]
        assert report["genre"] == "fantasy"
        assert report["phase"] == "draft"


class TestDataFetchers:
    async def test_fetch_without_repo(self):
        calc = make_calc()
        assert await calc._fetch_plot(1, 1) is None
        assert await calc._fetch_chapter(1, 1) is None
        assert await calc._fetch_illustration(1, 1) is None
        assert await calc._fetch_bible(1) is None
        assert await calc._fetch_audit_report(1, 1) is None

    async def test_fetch_repo_without_session(self):
        repo = MagicMock(spec=[])
        calc = make_calc(repository=repo)
        assert await calc._fetch_plot(1, 1) is None
        assert await calc._fetch_chapter(1, 1) is None
        assert await calc._fetch_illustration(1, 1) is None
        assert await calc._fetch_bible(1) is None
        assert await calc._fetch_audit_report(1, 1) is None

    async def test_fetch_success(self):
        repo = make_repo(plot="P", chapter="C", illustration="I", bible="B", audit=["a"])
        calc = make_calc(repository=repo)
        assert await calc._fetch_plot(1, 1) == "P"
        assert await calc._fetch_chapter(1, 1) == "C"
        assert await calc._fetch_illustration(1, 1) == "I"
        assert await calc._fetch_bible(1) == "B"
        assert await calc._fetch_audit_report(1, 1) == ["a"]

    async def test_fetch_error_returns_none(self):
        repo = MagicMock()
        repo.session = MagicMock()
        repo.session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        calc = make_calc(repository=repo)
        assert await calc._fetch_plot(1, 1) is None
        assert await calc._fetch_chapter(1, 1) is None
        assert await calc._fetch_illustration(1, 1) is None
        assert await calc._fetch_bible(1) is None
        assert await calc._fetch_audit_report(1, 1) is None


class TestStructureScoring:
    async def test_default_without_repo(self):
        assert await make_calc()._score_structure(1, 1, None) == 50.0

    async def test_default_no_data(self):
        calc = make_calc(repository=make_repo())
        assert await calc._score_structure(1, 1, None) == 70.0 * 0.35 + 70.0 * 0.35 + 70.0 * 0.30

    async def test_both_audits_pass(self):
        repo = make_repo(
            audit=[
                issue("logical_consistency", "low"),
                issue("causal_integrity", "medium"),
            ]
        )
        calc = make_calc(repository=repo)
        assert await calc._score_structure(1, 1, None) == 95.0 * 0.35 + 70.0 * 0.35 + 70.0 * 0.30

    async def test_one_audit_pass(self):
        repo = make_repo(audit=[issue("logical_consistency", "low")])
        calc = make_calc(repository=repo)
        assert await calc._score_structure(1, 1, None) == 75.0 * 0.35 + 70.0 * 0.35 + 70.0 * 0.30

    async def test_audits_fail(self):
        repo = make_repo(audit=[issue("logical_consistency", "high"), issue("causal_integrity", "high")])
        calc = make_calc(repository=repo)
        assert await calc._score_structure(1, 1, None) == 40.0 * 0.35 + 70.0 * 0.35 + 70.0 * 0.30

    @pytest.mark.parametrize("chapter_no,arc_score", [(10, 95.0), (12, 80.0), (20, 60.0)])
    async def test_arc_proximity(self, chapter_no, arc_score):
        plot = MagicMock()
        plot.end_ep = 10
        repo = make_repo(plot=plot)
        calc = make_calc(repository=repo)
        expected = 70.0 * 0.35 + arc_score * 0.35 + 70.0 * 0.30
        assert await calc._score_structure(1, chapter_no, None) == expected

    async def test_arc_end_zero_uses_default(self):
        plot = MagicMock()
        plot.end_ep = 0
        repo = make_repo(plot=plot)
        calc = make_calc(repository=repo)
        assert await calc._score_structure(1, 1, None) == 70.0

    @pytest.mark.parametrize("tension,pacing", [(50, 90.0), (25, 75.0), (95, 50.0)])
    async def test_tension_band(self, tension, pacing):
        repo = make_repo(chapter=chapter_obj(tension=tension))
        calc = make_calc(repository=repo)
        expected = 70.0 * 0.35 + 70.0 * 0.35 + pacing * 0.30
        assert await calc._score_structure(1, 1, None) == expected

    async def test_chapter_without_tension_attr(self):
        ch = MagicMock(spec=[])
        repo = make_repo(chapter=ch)
        calc = make_calc(repository=repo)
        assert await calc._score_structure(1, 1, None) == 70.0

    async def test_exception_falls_back(self):
        repo = make_repo()
        calc = make_calc(repository=repo)
        calc._fetch_audit_report = AsyncMock(side_effect=RuntimeError("x"))
        assert await calc._score_structure(1, 1, None) == 50.0


class TestCoherencyScoring:
    async def test_default_without_repo(self):
        assert await make_calc()._score_coherency(1, 1, None) == 50.0

    async def test_no_audit_no_content(self):
        # With no audit report at all, every sub-score keeps its 70.0 default.
        calc = make_calc(repository=make_repo())
        assert await calc._score_coherency(1, 1, None) == 70.0

    @pytest.mark.parametrize(
        "category,expected_speech",
        [
            ("speech_style", 75.0),
            ("dialogue_tone", 75.0),
            ("other", 95.0),
        ],
    )
    async def test_speech_issues(self, category, expected_speech):
        repo = make_repo(audit=[issue(category)])
        calc = make_calc(repository=repo)
        assert await calc._score_coherency(1, 1, None) == expected_speech * 0.3 + 95.0 * 0.3 + 95.0 * 0.2 + 70.0 * 0.2

    async def test_multiple_speech_issues(self):
        repo = make_repo(audit=[issue("speech"), issue("dialogue")])
        calc = make_calc(repository=repo)
        assert await calc._score_coherency(1, 1, None) == 50.0 * 0.3 + 95.0 * 0.3 + 95.0 * 0.2 + 70.0 * 0.2

    async def test_description_keyword_speech(self):
        repo = make_repo(audit=[issue("misc", description="口調_fun")])
        calc = make_calc(repository=repo)
        assert await calc._score_coherency(1, 1, None) == 75.0 * 0.3 + 95.0 * 0.3 + 95.0 * 0.2 + 70.0 * 0.2

    async def test_ability_issues(self):
        repo = make_repo(audit=[issue("ability_check")])
        calc = make_calc(repository=repo)
        assert await calc._score_coherency(1, 1, None) == 95.0 * 0.3 + 75.0 * 0.3 + 95.0 * 0.2 + 70.0 * 0.2

    async def test_ability_description_keyword(self):
        repo = make_repo(audit=[issue("misc", description="能力problem")])
        calc = make_calc(repository=repo)
        assert await calc._score_coherency(1, 1, None) == 95.0 * 0.3 + 75.0 * 0.3 + 95.0 * 0.2 + 70.0 * 0.2

    async def test_multiple_ability_issues(self):
        repo = make_repo(audit=[issue("ability_a"), issue("ability_b")])
        calc = make_calc(repository=repo)
        assert await calc._score_coherency(1, 1, None) == 95.0 * 0.3 + 50.0 * 0.3 + 95.0 * 0.2 + 70.0 * 0.2

    async def test_causal_issues(self):
        repo = make_repo(audit=[issue("causal_check")])
        calc = make_calc(repository=repo)
        assert await calc._score_coherency(1, 1, None) == 95.0 * 0.3 + 95.0 * 0.3 + 75.0 * 0.2 + 70.0 * 0.2

    async def test_multiple_causal_issues(self):
        repo = make_repo(audit=[issue("causal_a"), issue("causal_b")])
        calc = make_calc(repository=repo)
        assert await calc._score_coherency(1, 1, None) == 95.0 * 0.3 + 95.0 * 0.3 + 50.0 * 0.2 + 70.0 * 0.2

    async def test_causal_description_keyword(self):
        repo = make_repo(audit=[issue("misc", description="因果issue")])
        calc = make_calc(repository=repo)
        assert await calc._score_coherency(1, 1, None) == 95.0 * 0.3 + 95.0 * 0.3 + 75.0 * 0.2 + 70.0 * 0.2

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("テストテストテストテスト", 95.0),
            ("alpha beta gamma delta epsilon", 70.0),
            ("テスト テスト テスト あ い う え お", 80.0),
            ("あいうえおかきくけこさしすせそたちつてとなにぬ", 95.0),
        ],
    )
    async def test_naming_consistency(self, text, expected):
        repo = make_repo(chapter=chapter_obj(content=text))
        calc = make_calc(repository=repo)
        result = await calc._score_coherency(1, 1, None)
        # No audit report -> speech/world/timeline keep their 70.0 default.
        assert result == pytest.approx(70.0 * 0.8 + expected * 0.2)

    async def test_naming_low_ratio(self):
        repo = make_repo(chapter=chapter_obj(content="一 二 三 四 五 六"))
        calc = make_calc(repository=repo)
        result = await calc._score_coherency(1, 1, None)
        assert result < 95.0

    async def test_exception_falls_back(self):
        repo = make_repo()
        calc = make_calc(repository=repo)
        calc._fetch_audit_report = AsyncMock(side_effect=RuntimeError("x"))
        assert await calc._score_coherency(1, 1, None) == 50.0


class TestFactualScoring:
    def bible(self, settings):
        b = MagicMock()
        b.settings = settings
        return b

    async def test_unavailable_without_repo(self):
        with pytest.raises(ScoringUnavailableError):
            await make_calc()._score_factual(1, 1, None)

    async def test_defaults_no_data(self):
        # NOTE: with a chapter present but no bible, all sub-scores stay at their defaults.
        calc = make_calc(repository=make_repo(chapter=chapter_obj(content="本文")))
        assert await calc._score_factual(1, 1, None) == 70.0

    async def test_no_chapter_and_no_bible_raises_unavailable(self):
        # `bible` is only bound inside the `if chapter.content` branch; with neither
        # chapter nor bible the historical-accuracy check raises UnboundLocalError which
        # the service converts to ScoringUnavailableError.
        calc = make_calc(repository=make_repo())
        with pytest.raises(ScoringUnavailableError):
            await calc._score_factual(1, 1, None)

    async def test_rag_high_coverage(self):
        text = "魔術学院の物語。皇帝の秘密。騎士団の戦い。"
        repo = make_repo(
            chapter=chapter_obj(content=text),
            bible=self.bible(json.dumps({"world": "魔術学院 皇帝 騎士団", "x": 5}, ensure_ascii=False)),
        )
        calc = make_calc(repository=repo)
        expected = 95.0 * 0.4 + 95.0 * 0.35 + 70.0 * 0.25
        assert await calc._score_factual(1, 1, None) == expected

    async def test_rag_medium_coverage(self):
        text = "魔術学院の物語。" + "無関係" * 30
        repo = make_repo(
            chapter=chapter_obj(content=text),
            bible=self.bible(json.dumps({"w": "魔術学院 皇帝 騎士団 完全別の言葉 別の語", "x": 5}, ensure_ascii=False)),
        )
        calc = make_calc(repository=repo)
        result = await calc._score_factual(1, 1, None)
        # only 1 of 5 keywords is present -> low coverage bucket
        assert result == pytest.approx(50.0 * 0.4 + 95.0 * 0.35 + 70.0 * 0.25)

    async def test_rag_low_coverage(self):
        text = "無関係" * 40
        repo = make_repo(
            chapter=chapter_obj(content=text),
            bible=self.bible(json.dumps({"w": "完全不同 別物 別 別々", "y": 6}, ensure_ascii=False)),
        )
        calc = make_calc(repository=repo)
        result = await calc._score_factual(1, 1, None)
        assert 50.0 * 0.4 <= result

    async def test_bible_settings_dict_not_str(self):
        text = "皇帝の物語。" + " filler" * 40
        repo = make_repo(chapter=chapter_obj(content=text), bible=self.bible({"w": "皇帝"}))
        calc = make_calc(repository=repo)
        assert await calc._score_factual(1, 1, None) > 0

    async def test_invalid_json_raises(self):
        repo = make_repo(chapter=chapter_obj(content="本文"), bible=self.bible("{not json"))
        calc = make_calc(repository=repo)
        with pytest.raises(ScoringUnavailableError):
            await calc._score_factual(1, 1, None)

    async def test_anachronism_single(self):
        text = "彼は電話をかけた。"
        repo = make_repo(chapter=chapter_obj(content=text), bible=self.bible(json.dumps({"period": "medieval"})))
        calc = make_calc(repository=repo)
        assert await calc._score_factual(1, 1, None) == 70.0 * 0.4 + 75.0 * 0.35 + 70.0 * 0.25

    async def test_anachronisms_multiple(self):
        text = "彼は電話と自動車を使った。"
        repo = make_repo(chapter=chapter_obj(content=text), bible=self.bible(json.dumps({"時代": "edo"})))
        calc = make_calc(repository=repo)
        assert await calc._score_factual(1, 1, None) == 70.0 * 0.4 + 50.0 * 0.35 + 70.0 * 0.25

    async def test_glossary_high_usage(self):
        text = "魔術師と精霊的国家。" + " filler" * 40
        settings = {"period": "medieval", "glossary": {"魔術師": 1, "精霊": 1, "国家": 1}}
        repo = make_repo(chapter=chapter_obj(content=text), bible=self.bible(json.dumps(settings, ensure_ascii=False)))
        calc = make_calc(repository=repo)
        assert await calc._score_factual(1, 1, None) == 70.0 * 0.4 + 95.0 * 0.35 + 95.0 * 0.25

    async def test_glossary_medium_usage(self):
        text = "魔術師がいた。" + " filler" * 40
        settings = {"glossary": {"魔術師": 1, "精霊": 1, "国家": 1, "神器": 1}}
        repo = make_repo(chapter=chapter_obj(content=text), bible=self.bible(json.dumps(settings, ensure_ascii=False)))
        calc = make_calc(repository=repo)
        assert await calc._score_factual(1, 1, None) == 70.0 * 0.4 + 95.0 * 0.35 + 80.0 * 0.25

    async def test_glossary_low_usage(self):
        text = "無関係" * 40
        settings = {"glossary": {"甲": 1, "乙": 1, "丙": 1}}
        repo = make_repo(chapter=chapter_obj(content=text), bible=self.bible(json.dumps(settings, ensure_ascii=False)))
        calc = make_calc(repository=repo)
        assert await calc._score_factual(1, 1, None) == 70.0 * 0.4 + 95.0 * 0.35 + 60.0 * 0.25

    async def test_empty_glossary(self):
        text = "無関係" * 40
        repo = make_repo(chapter=chapter_obj(content=text), bible=self.bible(json.dumps({"period": "futuristic", "glossary": {}})))
        calc = make_calc(repository=repo)
        assert await calc._score_factual(1, 1, None) == 70.0 * 0.4 + 95.0 * 0.35 + 70.0 * 0.25

    async def test_generic_error_wrapped(self):
        repo = make_repo()
        calc = make_calc(repository=repo)
        calc._fetch_chapter = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(ScoringUnavailableError):
            await calc._score_factual(1, 1, None)

    def test_anachronism_lookup(self):
        calc = make_calc()
        assert calc._get_anachronisms("futuristic") == []
        assert calc._get_anachronisms("unknown-period") == []
        assert "拳銃" in calc._get_anachronisms("medieval")
        assert "馬車" in calc._get_anachronisms("modern")


class TestVisualTextualScoring:
    async def test_default_without_repo(self):
        assert await make_calc()._score_visual_textual(1, 1, None) == 50.0

    async def test_missing_illustration(self):
        repo = make_repo(chapter=chapter_obj(content="本文"))
        assert await make_calc(repository=repo)._score_visual_textual(1, 1, None) == 50.0

    async def test_missing_chapter(self):
        repo = make_repo(illustration=MagicMock(prompt="x"))
        assert await make_calc(repository=repo)._score_visual_textual(1, 1, None) == 50.0

    async def test_empty_content(self):
        repo = make_repo(illustration=MagicMock(prompt="x"), chapter=chapter_obj(content=""))
        assert await make_calc(repository=repo)._score_visual_textual(1, 1, None) == 50.0

    async def test_empty_prompt(self):
        repo = make_repo(illustration=MagicMock(prompt=""), chapter=chapter_obj(content="本文"))
        assert await make_calc(repository=repo)._score_visual_textual(1, 1, None) == 50.0

    async def test_none_prompt(self):
        repo = make_repo(illustration=MagicMock(prompt=None), chapter=chapter_obj(content="本文"))
        assert await make_calc(repository=repo)._score_visual_textual(1, 1, None) == 50.0

    async def test_high_jaccard_matched_tone(self):
        text = "皇帝の悲しみを HABIT bright light happy"
        prompt = "皇帝 悲しみ bright light happy focus highlight"
        repo = make_repo(
            illustration=MagicMock(prompt=prompt),
            chapter=chapter_obj(content=text),
        )
        calc = make_calc(repository=repo)
        result = await calc._score_visual_textual(1, 1, None)
        assert result == pytest.approx(70.75)

    async def test_medium_jaccard(self):
        text = "皇帝 悲しみ 物語 冬天"
        prompt = "皇帝 悲しみ 雪 山 風"
        repo = make_repo(illustration=MagicMock(prompt=prompt), chapter=chapter_obj(content=text))
        calc = make_calc(repository=repo)
        result = await calc._score_visual_textual(1, 1, None)
        assert 65.0 <= result <= 90.0

    async def test_low_jaccard_and_mismatched_tone(self):
        text = "皇帝 悲しみ 物語 冬天"
        prompt = "completely different words bright happy joy"
        repo = make_repo(illustration=MagicMock(prompt=prompt), chapter=chapter_obj(content=text))
        calc = make_calc(repository=repo)
        result = await calc._score_visual_textual(1, 1, None)
        assert result == pytest.approx(47.5)

    async def test_text_focus_only(self):
        text = "彼は叫んだ！！「あああ」――"
        prompt = "皇帝 悲しみ 物語 冬天"
        repo = make_repo(illustration=MagicMock(prompt=prompt), chapter=chapter_obj(content=text))
        calc = make_calc(repository=repo)
        result = await calc._score_visual_textual(1, 1, None)
        assert result == pytest.approx(66.5)

    async def test_no_focus(self):
        text = "皇帝 悲しみ 物語 冬天"
        prompt = "皇帝 悲しみ 物語 冬山 風車"
        repo = make_repo(illustration=MagicMock(prompt=prompt), chapter=chapter_obj(content=text))
        calc = make_calc(repository=repo)
        result = await calc._score_visual_textual(1, 1, None)
        assert result == pytest.approx(67.0)

    async def test_exception_falls_back(self):
        repo = make_repo(illustration=MagicMock(prompt="x"), chapter=chapter_obj(content="y"))
        calc = make_calc(repository=repo)
        calc._fetch_illustration = AsyncMock(side_effect=RuntimeError("x"))
        assert await calc._score_visual_textual(1, 1, None) == 50.0


class TestReaderExperience:
    async def test_default_without_repo(self):
        assert await make_calc()._score_reader_experience(1, 1, None) == 50.0

    async def test_missing_chapter(self):
        assert await make_calc(repository=make_repo())._score_reader_experience(1, 1, None) == 50.0

    async def test_short_text_no_hook_scores(self):
        repo = make_repo(chapter=chapter_obj(content="短い。"))
        calc = make_calc(repository=repo)
        assert await calc._score_reader_experience(1, 1, None) == 50.0 * 0.4 + 50.0 * 0.35 + 50.0 * 0.25

    async def test_dense_hook_keywords(self):
        text = "なぜ？" * 40
        repo = make_repo(chapter=chapter_obj(content=text, tension=50))
        calc = make_calc(repository=repo)
        result = await calc._score_reader_experience(1, 1, None)
        assert result > 50.0

    async def test_sparse_hook_keywords(self):
        text = "彼は静かに歩いた。" * 20
        repo = make_repo(chapter=chapter_obj(content=text, tension=50))
        calc = make_calc(repository=repo)
        result = await calc._score_reader_experience(1, 1, None)
        assert result < 90.0

    @pytest.mark.parametrize("tension,emotion", [(50, 85.0), (20, 70.0), (98, 50.0)])
    async def test_tension_bands(self, tension, emotion):
        text = "彼は静かに歩いた。" * 20
        repo = make_repo(chapter=chapter_obj(content=text, tension=tension))
        calc = make_calc(repository=repo)
        result = await calc._score_reader_experience(1, 1, None)
        assert result == pytest.approx(40.0 * 0.4 + 40.0 * 0.35 + emotion * 0.25)

    async def test_no_tension_uses_sentence_variance(self):
        text = "短い。次。中程度。" + "とても長い文章をここに書いています。" * 10 + "終わり。"
        repo = make_repo(chapter=chapter_obj(content=text, tension=None))
        calc = make_calc(repository=repo)
        result = await calc._score_reader_experience(1, 1, None)
        assert result > 0

    async def test_no_tension_few_sentences(self):
        repo = make_repo(chapter=chapter_obj(content="あ。い。", tension=None))
        calc = make_calc(repository=repo)
        result = await calc._score_reader_experience(1, 1, None)
        assert result == pytest.approx(50.0)

    async def test_exception_falls_back(self):
        repo = make_repo(chapter=chapter_obj(content="本文"))
        calc = make_calc(repository=repo)
        calc._fetch_chapter = AsyncMock(side_effect=RuntimeError("x"))
        assert await calc._score_reader_experience(1, 1, None) == 50.0


class TestCalculate:
    async def test_calculate_without_repo(self):
        score = await make_calc().calculate(1, 1)
        assert isinstance(score, BookScore)
        assert score.structure_score == 50.0

    async def test_calculate_neutral_on_factual_failure(self):
        repo = make_repo(chapter=chapter_obj(content="本文", tension=50))
        calc = make_calc(repository=repo)
        calc._score_factual = AsyncMock(side_effect=ScoringUnavailableError("nope"))
        score = await calc.calculate(1, 1)
        assert score.factual_grounding_score == NEUTRAL_SCORE

    async def test_calculate_saves_when_repo(self):
        repo = make_repo()
        calc = make_calc(repository=repo)
        await calc.calculate(1, 2)
        repo.save.assert_awaited_once()
        model = repo.save.await_args.args[0]
        assert model.book_id == 1
        assert model.chapter_number == 2
        assert model.evaluator_version == "1.0"

    async def test_calculate_custom_weights(self):
        calc = make_calc()
        calc._get_weights = MagicMock(return_value={
            "structure": 50, "coherency": 20, "factual_grounding": 10,
            "visual_textual_synergy": 10, "reader_experience": 10,
        })
        calc._score_structure = AsyncMock(return_value=100.0)
        calc._score_coherency = AsyncMock(return_value=0.0)
        calc._score_factual = AsyncMock(return_value=0.0)
        calc._score_visual_textual = AsyncMock(return_value=0.0)
        calc._score_reader_experience = AsyncMock(return_value=0.0)
        score = await calc.calculate(1, 1, genre="x", phase="y")
        assert score.overall_score == 50.0

    async def test_calculate_default_weights_keys_missing(self):
        calc = make_calc()
        calc._get_weights = MagicMock(return_value={})
        score = await calc.calculate(1, 1)
        # `weights.get("factual_grounding", 20)` -> 20。repository 無しのとき factual は
        # 評価できないので `ScoringUnavailableError` になり、NEUTRAL_SCORE(100.0) として
        # **表示値だけ** 设置される（低スコアに偽装しない、という既存意図は維持）。
        #
        # 総合スコアは「評価できた次元の重み付き平均」であるため、欠測した factual を
        # 分子・分母の両方から除外して再正規化する。旧実装は unavailable を満点 100 として
        # 分子に足していたため、1 次元分だけスコアが 60 持ち上がった（障害の高評価化）。
        # `test_calculate_without_repository_defaults_to_50` と同じ条件で 50.0 を期待する。
        assert score.factual_grounding_score == NEUTRAL_SCORE
        available = 0.25 + 0.25 + 0.15 + 0.15
        expected = (50.0 * 0.25 + 50.0 * 0.25 + 50.0 * 0.15 + 50.0 * 0.15) / available
        assert score.overall_score == round(expected, 2)
        assert score.overall_score == 50.0


class TestPersistence:
    async def test_save_without_repo(self):
        await make_calc().save_score(1, 1, BookScore(1, 2, 3, 4, 5, 6))

    async def test_save_with_repo(self):
        repo = make_repo()
        calc = make_calc(repository=repo)
        await calc.save_score(1, 1, BookScore(1, 2, 3, 4, 5, 6, {"a": 1}), evaluator_version="2.0")
        model = repo.save.await_args.args[0]
        assert model.specialist_breakdown == {"a": 1}
        assert model.evaluator_version == "2.0"

    async def test_get_latest_without_repo(self):
        assert await make_calc().get_latest_score(1, 1) is None

    async def test_get_latest_with_repo(self):
        repo = make_repo()
        repo.get_latest.return_value = "LATEST"
        assert await make_calc(repository=repo).get_latest_score(1, 1) == "LATEST"


class TestTextStats:
    async def test_empty(self):
        stats = await make_calc()._build_text_stats("")
        assert stats == {"char_count": 0, "word_count": 0, "sentence_count": 0, "avg_sentence_length": 0.0}

    async def test_populated(self):
        text = "One two. Three! Four?"
        stats = await make_calc()._build_text_stats(text)
        assert stats["char_count"] == len(text)
        assert stats["word_count"] == 4
        assert stats["sentence_count"] == 3
        assert stats["avg_sentence_length"] == len(text) / 3


class TestTrend:
    def scores(self, values):
        return [MagicMock(overall_score=v) for v in values]

    async def test_no_repo(self):
        assert await make_calc().analyze_trend(1) == {"error": "Repository not configured"}

    async def test_insufficient_data(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = self.scores([1.0, 2.0])
        result = await make_calc(repository=repo).analyze_trend(1)
        assert "error" in result
        assert result["chapters_evaluated"] == 2

    async def test_improving_trend(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = self.scores([10.0, 40.0, 70.0, 95.0, 100.0])
        result = await make_calc(repository=repo).analyze_trend(1)
        assert result["trend_direction"] == "improving"
        assert result["slope"] > 0
        assert len(result["moving_avg_3"]) == 3
        assert result["r_squared"] == pytest.approx(0.9554)
        assert result["next_chapter_prediction"] > 0
        assert result["latest_score"] == 100.0
        assert result["avg_score"] == 63.0

    async def test_declining_trend(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = self.scores([100.0, 80.0, 60.0, 40.0])
        result = await make_calc(repository=repo).analyze_trend(1)
        assert result["trend_direction"] == "declining"

    async def test_stable_trend(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = self.scores([50.0, 50.5, 50.2, 50.1])
        result = await make_calc(repository=repo).analyze_trend(1)
        assert result["trend_direction"] == "stable"

    async def test_changepoints_detected(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = self.scores([50.0, 90.0, 55.0, 20.0])
        result = await make_calc(repository=repo).analyze_trend(1)
        assert len(result["changepoints"]) == 3
        assert result["changepoints"][0]["chapter_index"] == 1
        assert result["changepoints"][0]["change"] == 40.0

    async def test_window_limit(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = self.scores([float(i) for i in range(20)])
        result = await make_calc(repository=repo).analyze_trend(1, window=5)
        assert result["chapters_evaluated"] == 5

    async def test_flat_scores_r_squared_zero(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = self.scores([50.0, 50.0, 50.0])
        result = await make_calc(repository=repo).analyze_trend(1)
        assert result["r_squared"] == 0

    async def test_window_larger_than_data(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = self.scores([1.0, 2.0, 3.0])
        result = await make_calc(repository=repo).analyze_trend(1, window=10)
        assert result["chapters_evaluated"] == 3


class TestPdcaReport:
    async def test_trend_error(self):
        result = await make_calc().generate_pdca_report(1)
        assert result == {"error": "Repository not configured", "book_id": 1}

    def score_model(self, overall, structure=50, coherency=50, factual=50, visual=50, reader=50):
        return MagicMock(
            overall_score=overall,
            structure_score=structure,
            coherency_score=coherency,
            factual_grounding_score=factual,
            visual_textual_synergy_score=visual,
            reader_experience_score=reader,
        )

    async def test_full_report(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = [
            self.score_model(90.0, 30.0),
            self.score_model(50.0, 40.0),
            self.score_model(10.0, 65.0),
        ]
        report = await make_calc(repository=repo).generate_pdca_report(1)
        assert report["book_id"] == 1
        assert report["plan"]["target_score"] == 80.0
        assert report["check"]["target_achieved"] is False
        assert report["do"]["trend_direction"] == "declining"
        actions = [a["action"] for a in report["act"]["recommended_actions"]]
        assert "investigate_decline" in actions
        assert "improve_structure" in actions
        assert "improve_coherency" in actions
        # sorted by gap descending: coherency (gap 20) before structure (gap 5)
        assert report["plan"]["priority_dimensions"][0]["dimension"] == "coherency"
        # investigate_decline is appended first with high priority
        assert report["act"]["recommended_actions"][0]["action"] == "investigate_decline"
        assert report["act"]["recommended_actions"][0]["priority"] == "high"

    async def test_changepoint_action(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = [
            self.score_model(50.0),
            self.score_model(90.0),
            self.score_model(55.0),
        ]
        report = await make_calc(repository=repo).generate_pdca_report(1)
        assert "review_changepoints" in [a["action"] for a in report["act"]["recommended_actions"]]

    async def test_improving_report(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = [
            self.score_model(80.0, 80.0, 80.0, 80.0, 80.0, 80.0),
            self.score_model(85.0, 80.0, 80.0, 80.0, 80.0, 80.0),
            self.score_model(90.0, 80.0, 80.0, 80.0, 80.0, 80.0),
        ]
        report = await make_calc(repository=repo).generate_pdca_report(1)
        assert report["check"]["target_achieved"] is True
        assert report["check"]["trend_improving"] is True
        assert report["plan"]["priority_dimensions"] == []
        assert report["act"]["recommended_actions"] == []
        assert report["plan"]["gap"] == -5.0

    async def test_all_dimensions_above_seventy(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = [
            self.score_model(50.0, 80.0, 80.0, 80.0, 80.0, 80.0),
            self.score_model(50.0, 80.0, 80.0, 80.0, 80.0, 80.0),
            self.score_model(50.0, 80.0, 80.0, 80.0, 80.0, 80.0),
        ]
        calc = make_calc(repository=repo)
        report = await calc.generate_pdca_report(1)
        assert report["plan"]["priority_dimensions"] == []
        assert report["act"]["recommended_actions"] == []
        assert report["do"]["trend_direction"] == "stable"

    async def test_medium_gap_priority(self):
        repo = make_repo()
        repo.get_all_for_book.return_value = [
            self.score_model(80.0),
            self.score_model(82.0),
            self.score_model(84.0, structure=55.0),
        ]
        report = await make_calc(repository=repo).generate_pdca_report(1)
        action = next(a for a in report["act"]["recommended_actions"] if a["action"] == "improve_structure")
        assert action["priority"] == "medium"
