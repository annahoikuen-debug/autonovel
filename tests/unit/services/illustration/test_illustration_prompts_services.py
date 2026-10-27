"""Unit tests for illustration prompts, model_selector, and *Service classes."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.illustration import (
    IllustrationModel,
    IllustrationRequest,
    IllustrationType,
    SafetyLevel,
)
from src.services.illustration.character_service import CharacterIllustrator
from src.services.illustration.cover_service import CoverGenerator
from src.services.illustration.model_selector import (
    is_r15,
    resolve_model_id,
    resolve_request_model,
)
from src.services.illustration.prompts import (
    apply_safety_modifier,
    apply_yonkoma_safety_modifier,
    build_character_prompt,
    build_cover_prompt,
    build_scene_prompt,
    build_yonkoma_prompt,
)
from src.services.illustration.scene_service import (
    SceneExtractor,
    SceneIllustrator,
    SceneIllustrationService,
    YonkomaIllustrator,
    YonkomaPlanner,
)


class _StrVal:
    """enum ライクなオブジェクト（別モジュール由来の enum を模したテスト用）"""

    def __init__(self, value):
        self.value = value


class TestPromptHelpers:
    @pytest.mark.parametrize(
        "genre,expected_fragment",
        [
            ("ファンタジー", "epic fantasy art style"),
            ("異世界ラブコメ", "soft pastel shoujo style"),
            ("hard SF", "futuristic sci-fi style"),
            ("ホラー", "dark gothic horror style"),
            ("ミステリー", "noir mystery style"),
            ("歴史物", "historical painterly style"),
            ("ライトノベル", "modern light novel cover style"),
            ("未知のジャンル", "未知のジャンル themed illustration style"),
        ],
    )
    def test_genre_hint(self, genre, expected_fragment):
        from src.services.illustration.prompts import _genre_hint

        assert expected_fragment in _genre_hint(genre)

    def test_genre_hint_empty(self):
        from src.services.illustration.prompts import _genre_hint

        assert "modern light novel cover style" in _genre_hint("")

    def test_cover_prompt_minimal(self):
        out = build_cover_prompt({})
        assert "Untitled" in out
        assert "Professional novel book cover illustration." in out
        assert "no text or letters in image." in out
        assert "Story concept" not in out

    def test_cover_prompt_full(self):
        out = build_cover_prompt(
            {
                "title": "星降る夜",
                "genre": "SF",
                "concept": "少女が機械人心做到む",
                "keywords": "星, 機械",
            }
        )
        assert "Title theme: 星降る夜." in out
        assert "futuristic sci-fi style" in out
        assert "Story concept: 少女が機械人心做到む" in out
        assert "Visual motifs: 星, 機械" in out

    @pytest.mark.parametrize("variation", [0, 1, 2, 3, 4])
    def test_cover_variations_wrap(self, variation):
        out = build_cover_prompt({"title": "T"}, variation=variation)
        assert out.startswith("Professional novel book cover illustration.")

    def test_scene_prompt(self):
        out = build_scene_prompt("  街の灯り  ", {"genre": "ホラー"})
        assert "dark gothic horror style" in out
        assert "Scene description: 街の灯り" in out
        assert "Cinematic lighting" in out

    def test_scene_prompt_truncates(self):
        out = build_scene_prompt("あ" * 500, {})
        assert "..." in out
        assert len(out) < 700

    def test_character_prompt_minimal(self):
        out = build_character_prompt({})
        assert "Character name: character." in out
        assert "Detailed original character design." in out
        assert "Role:" not in out

    def test_character_prompt_full(self):
        out = build_character_prompt(
            {
                "name": "アオイ",
                "role": "主人公",
                "appearance": "青い髪",
                "traits": "クール",
                "background": "学園",
            }
        )
        assert "Character name: アオイ." in out
        assert "Role: 主人公." in out
        assert "Appearance: 青い髪." in out
        assert "Personality reflected in expression: クール." in out
        assert "Setting hint: 学園." in out

    @pytest.mark.parametrize(
        "safety,changed",
        [
            (SafetyLevel.BLOCK_MOST, False),
            (SafetyLevel.BLOCK_SOME, False),
            (SafetyLevel.BLOCK_FEW, False),
            (SafetyLevel.R15_CONTENT, True),
        ],
    )
    def test_apply_safety_modifier_scene(self, safety, changed):
        out = apply_safety_modifier("BASE", safety, IllustrationType.EPISODE)
        assert (out != "BASE") is changed

    def test_apply_safety_modifier_character_variant(self):
        out = apply_safety_modifier("BASE", SafetyLevel.R15_CONTENT, IllustrationType.CHARACTER)
        assert "romantic atmosphere" in out
        assert "elegant and non-explicit." in out

    def test_apply_safety_modifier_non_enum(self):
        out = apply_safety_modifier("BASE", _StrVal("R15_CONTENT"), IllustrationType.EPISODE)
        assert out != "BASE"
        assert "intimate but not explicit" in out

    def test_apply_safety_modifier_duck_typed_non_r15(self):
        assert apply_safety_modifier("BASE", _StrVal("BLOCK_SOME"), IllustrationType.COVER) == "BASE"

    def test_apply_safety_modifier_bare_string(self):
        assert apply_safety_modifier("BASE", "BLOCK_SOME", IllustrationType.COVER) == "BASE"
        assert apply_safety_modifier("BASE", "R15_CONTENT", IllustrationType.COVER) != "BASE"

    def test_yonkoma_safety_modifier(self):
        assert apply_yonkoma_safety_modifier("B", SafetyLevel.BLOCK_SOME) == "B"
        out = apply_yonkoma_safety_modifier("B", SafetyLevel.R15_CONTENT)
        assert "in all panels" in out
        out2 = apply_yonkoma_safety_modifier("B", "R15_CONTENT")
        assert "in all panels" in out2
        assert apply_yonkoma_safety_modifier("B", "BLOCK_FEW") == "B"


class TestBuildYonkomaPrompt:
    def test_six_panels(self):
        out = build_yonkoma_prompt([f"scene {i}" for i in range(6)], {"title": "T"})
        assert out.count("Panel ") >= 6
        assert "Work title: T." in out
        assert "No text or letters in image" in out

    def test_panels_clamped(self):
        assert "Panel 3 [" in build_yonkoma_prompt(["a"] * 6, {}, panels=3)
        assert "Panel 3 [" in build_yonkoma_prompt(["a"] * 6, {}, panels=99)
        assert "Panel 3 [" in build_yonkoma_prompt(["a"] * 6, {}, panels=0)
        assert "Panel 3 [" in build_yonkoma_prompt(["a"] * 6, {}, panels=None)

    def test_missing_summaries_default(self):
        out = build_yonkoma_prompt([], {}, panels=6)
        assert "(implicit progression based on previous panel)" in out

    def test_long_summary_truncated(self):
        out = build_yonkoma_prompt(["あ" * 300], {}, panels=3)
        assert "..." in out

    def test_none_summaries_default(self):
        out = build_yonkoma_prompt([None, "  ", "b"], {}, panels=3)
        assert "Scene: b." in out

    def test_empty_book_context(self):
        out = build_yonkoma_prompt(["a"], {}, panels=3)
        assert "Work title: Untitled." in out


class TestModelSelector:
    def test_is_r15(self):
        assert is_r15(SafetyLevel.R15_CONTENT) is True
        assert is_r15(SafetyLevel.BLOCK_SOME) is False
        assert is_r15("R15_CONTENT") is True
        assert is_r15(_StrVal("R15_CONTENT")) is True

    def test_resolve_model_id_auto(self):
        assert resolve_model_id(IllustrationModel.AUTO) == "imagen-4.0-fast-generate-001"

    def test_resolve_model_id_explicit(self):
        assert resolve_model_id(IllustrationModel.QUALITY) == "imagen-4.0-generate-001"
        assert resolve_model_id(IllustrationModel.ULTRA) == "imagen-4.0-ultra-generate-001"

    def test_resolve_model_id_string(self):
        assert resolve_model_id("fast") == "imagen-4.0-fast-generate-001"

    def test_resolve_model_id_duck_typed(self):
        class D:
            value = "ultra"

        assert resolve_model_id(D()) == "imagen-4.0-ultra-generate-001"

    def test_resolve_request_model_auto(self):
        req = IllustrationRequest(
            book_id=1,
            illustration_type=IllustrationType.COVER,
            safety_level=SafetyLevel.BLOCK_MOST,
        )
        assert resolve_request_model(req)

    def test_resolve_request_model_explicit(self):
        req = IllustrationRequest(
            book_id=1, illustration_type=IllustrationType.COVER, model=IllustrationModel.ULTRA
        )
        assert resolve_request_model(req) == "imagen-4.0-ultra-generate-001"

    def test_resolve_request_model_string_type(self):
        req = IllustrationRequest(
            book_id=1,
            illustration_type=_StrVal("cover"),
            model="quality",
            safety_level=_StrVal("BLOCK_SOME"),
        )
        assert resolve_request_model(req) == "imagen-4.0-generate-001"

    def test_attribute_error_fallbacks(self):
        class Raises:
            @property
            def value(self):
                raise AttributeError("no value")

        assert resolve_model_id(Raises()) == "imagen-4.0-fast-generate-001"
        assert is_r15(Raises()) is False

    def test_duck_typed_without_value_attribute(self):
        class Bare:
            pass

        assert resolve_model_id(Bare()) == "imagen-4.0-fast-generate-001"
        assert is_r15(Bare()) is False


class TestSceneExtractor:
    def test_extract_scenes_heuristic(self):
        text = (
            "夕暮れの街で、少女は空を見上げた。\n\n"
            "光る海が目の前に広がっていた。\n\n"
            "短い。\n"
        )
        scenes = SceneExtractor().extract_scenes(text, max_scenes=2)
        assert 1 <= len(scenes) <= 2
        assert all(len(s) >= 15 for s in scenes)

    def test_extract_scenes_empty(self):
        assert SceneExtractor().extract_scenes("") == []

    async def test_extract_scenes_with_llm_list(self):
        llm = MagicMock()
        llm.default_model = "gemini-x"
        llm.generate_json = AsyncMock(return_value=["a", "b", "c"])
        out = await SceneExtractor().extract_scenes_with_llm("body", llm, max_scenes=2)
        assert out == ["a", "b"]

    async def test_extract_scenes_with_llm_dict(self):
        llm = MagicMock()
        llm.generate_json = AsyncMock(
            return_value=MagicMock(metadata={"scenes": ["x", "y"]})
        )
        out = await SceneExtractor().extract_scenes_with_llm("body", llm)
        assert out == ["x", "y"]

    async def test_extract_scenes_with_llm_result_key(self):
        llm = MagicMock()
        llm.generate_json = AsyncMock(return_value=MagicMock(metadata={"result": ["z"]}))
        out = await SceneExtractor().extract_scenes_with_llm("body", llm)
        assert out == ["z"]

    async def test_extract_scenes_with_llm_failure_falls_back(self):
        llm = MagicMock()
        llm.generate_json = AsyncMock(side_effect=RuntimeError("llm down"))
        text = "夕暮れの街で、少女は空を見上げた。光る海が広がっていた。"
        out = await SceneExtractor().extract_scenes_with_llm(text, llm)
        assert isinstance(out, list)


class TestYonkomaPlanner:
    def test_plan_heuristic_enough_paragraphs(self):
        text = "\n\n".join([f"これは段落{i}です、十分長い文章。" for i in range(9)])
        out = YonkomaPlanner().plan_heuristic(text, panels=6)
        assert len(out) == 6

    def test_plan_heuristic_fewer_paragraphs(self):
        text = "一つの長い段落だけPortableHereの文章です。\n\n二段落目Portableの文章です。"
        out = YonkomaPlanner().plan_heuristic(text, panels=6)
        assert len(out) == 6
        assert out[0] != out[1]
        assert out[-1] == out[-2] == out[1]

    def test_plan_heuristic_no_paragraphs(self):
        out = YonkomaPlanner().plan_heuristic("", panels=4)
        assert out == ["(導入)"] * 4

    def test_plan_heuristic_panels_clamped(self):
        assert len(YonkomaPlanner().plan_heuristic("短い文章がながいです。", panels=1)) == 3
        assert len(YonkomaPlanner().plan_heuristic("短い文章がながいです。", panels=99)) == 6

    def test_normalize(self):
        assert YonkomaPlanner._normalize(["a", "b", "c"], 2) == ["a", "b"]
        assert YonkomaPlanner._normalize(["a"], 3) == ["a", "a", "a"]
        assert YonkomaPlanner._normalize([], 2) == ["(継続)", "(継続)"]

    async def test_plan_with_llm_success(self):
        llm = MagicMock()
        llm.default_model = "gemini-x"
        llm.generate_json = AsyncMock(return_value=MagicMock(metadata={"panels": ["p1", "p2"]}))
        out = await YonkomaPlanner().plan_with_llm("text", llm, panels=3)
        assert len(out) == 3
        assert out[0] == "p1"

    async def test_plan_with_llm_scenes_key(self):
        llm = MagicMock()
        llm.generate_json = AsyncMock(return_value=MagicMock(metadata={"scenes": ["s1"]}))
        out = await YonkomaPlanner().plan_with_llm("text", llm, panels=3)
        assert out[0] == "s1"

    async def test_plan_with_llm_failure_falls_back(self):
        llm = MagicMock()
        llm.generate_json = AsyncMock(side_effect=ValueError("nope"))
        out = await YonkomaPlanner().plan_with_llm("文本がながいです。", llm, panels=3)
        assert len(out) == 3

    async def test_plan_with_llm_empty_list_falls_back(self):
        llm = MagicMock()
        llm.generate_json = AsyncMock(return_value=MagicMock(metadata={"panels": ["", "  "]}))
        out = await YonkomaPlanner().plan_with_llm("文本がながいです。", llm, panels=3)
        assert len(out) == 3
        assert out[0] != ""


def _image_service(url="https://img/x.png"):
    svc = MagicMock()
    svc.generate = AsyncMock(return_value=url)
    return svc


class TestSceneIllustrator:
    async def test_generate_for_scene(self):
        svc = _image_service()
        req = IllustrationRequest(
            book_id=1,
            illustration_type=IllustrationType.EPISODE,
            scene_text="街の夜",
            book_context={"genre": "SF"},
        )
        res = await SceneIllustrator(svc).generate_for_scene("街の夜", req)
        assert res.image_url == "https://img/x.png"
        assert "Scene description" in res.prompt
        assert res.model_used
        assert res.generation_time_ms >= 0
        assert svc.generate.call_args.kwargs["aspect_ratio"] == "3:4"


class TestSceneIllustrationService:
    async def test_generate_without_llm(self):
        svc = _image_service()
        text = "夕暮れの街で少女は空を見上げた。光る海が目に広がった。雪が降っている。"
        req = IllustrationRequest(
            book_id=1, illustration_type=IllustrationType.EPISODE, scene_text=text
        )
        out = await SceneIllustrationService(svc).generate(req)
        assert isinstance(out, list)
        assert len(out) >= 1

    async def test_generate_with_llm(self):
        svc = _image_service()
        llm = MagicMock()
        llm.generate_json = AsyncMock(return_value=["scene one", "scene two"])
        req = IllustrationRequest(
            book_id=1, illustration_type=IllustrationType.EPISODE, scene_text="本文"
        )
        out = await SceneIllustrationService(svc, llm=llm).generate(req)
        assert len(out) == 2

    async def test_generate_empty_scene_text(self):
        svc = _image_service()
        req = IllustrationRequest(
            book_id=1, illustration_type=IllustrationType.EPISODE, scene_text=None
        )
        out = await SceneIllustrationService(svc).generate(req)
        assert out == []


class TestYonkomaIllustrator:
    async def test_generate_with_summaries(self):
        svc = _image_service()
        req = IllustrationRequest(
            book_id=1, illustration_type=IllustrationType.YONKOMA, book_context={"title": "T"}
        )
        res = await YonkomaIllustrator(svc).generate("本文", req, summaries=["a", "b"])
        assert "Panel 1" in res.prompt
        assert res.image_url == "https://img/x.png"
        assert svc.generate.call_args.kwargs["aspect_ratio"] == "3:4"

    async def test_generate_plans_when_summaries_none(self):
        svc = _image_service()
        req = IllustrationRequest(
            book_id=1, illustration_type=IllustrationType.YONKOMA, aspect_ratio="1:1"
        )
        res = await YonkomaIllustrator(svc).generate(
            "夕暮れの街で、少女は空を見上げた。\n\n光る海が広がっていた。",
            req,
            panels=4,
        )
        assert "Panel 4" in res.prompt
        assert svc.generate.call_args.kwargs["aspect_ratio"] == "1:1"

    async def test_generate_applies_r15(self):
        svc = _image_service()
        req = IllustrationRequest(
            book_id=1,
            illustration_type=IllustrationType.YONKOMA,
            safety_level=SafetyLevel.R15_CONTENT,
        )
        res = await YonkomaIllustrator(svc).generate("本文", req, summaries=["a"], panels=3)
        assert "R15" in res.prompt


class TestCoverGenerator:
    async def test_generate(self):
        svc = _image_service()
        req = IllustrationRequest(
            book_id=1,
            illustration_type=IllustrationType.COVER,
            book_context={"title": "T", "genre": "ホラー"},
            episode_number=1,
        )
        res = await CoverGenerator(svc).generate(req)
        assert "Professional novel book cover illustration." in res.prompt
        assert res.image_url == "https://img/x.png"
        assert res.generation_time_ms >= 0

    async def test_generate_uses_prompt_override(self):
        svc = _image_service()
        req = IllustrationRequest(
            book_id=1,
            illustration_type=IllustrationType.COVER,
            prompt_override="OVERRIDDEN",
        )
        res = await CoverGenerator(svc).generate(req)
        assert res.prompt.startswith("OVERRIDDEN")

    async def test_generate_uses_variation_from_episode(self):
        svc = _image_service()
        req = IllustrationRequest(
            book_id=1, illustration_type=IllustrationType.COVER, episode_number=1
        )
        res = await CoverGenerator(svc).generate(req)
        assert "wide cinematic shot" in res.prompt

    async def test_generate_variations(self):
        svc = _image_service()
        req = IllustrationRequest(
            book_id=1, illustration_type=IllustrationType.COVER, book_context={"title": "T"}
        )
        out = await CoverGenerator(svc).generate_variations(req, count=3)
        assert len(out) == 3
        assert [r.request.episode_number for r in out] == [0, 1, 2]


class TestCharacterIllustrator:
    async def test_generate(self):
        svc = _image_service()
        req = IllustrationRequest(
            book_id=1,
            illustration_type=IllustrationType.CHARACTER,
            book_context={"name": "アオイ", "role": "主人公"},
        )
        res = await CharacterIllustrator(svc).generate(req)
        assert "Full body character illustration" in res.prompt
        assert "Character name: アオイ." in res.prompt
        assert res.model_used

    async def test_generate_with_prompt_override(self):
        svc = _image_service()
        req = IllustrationRequest(
            book_id=1, illustration_type=IllustrationType.CHARACTER, prompt_override="OVERRIDE"
        )
        res = await CharacterIllustrator(svc).generate(req)
        assert res.prompt.startswith("OVERRIDE")

    async def test_generate_r15(self):
        svc = _image_service()
        req = IllustrationRequest(
            book_id=1,
            illustration_type=IllustrationType.CHARACTER,
            safety_level=SafetyLevel.R15_CONTENT,
            book_context={"name": "A"},
        )
        res = await CharacterIllustrator(svc).generate(req)
        assert "R15" in res.prompt
