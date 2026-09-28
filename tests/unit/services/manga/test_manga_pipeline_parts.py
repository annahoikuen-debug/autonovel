"""Unit tests for src/services/manga/{config,models,prompt_generator,quality_gate}."""
import os
from pathlib import Path

import pytest

from src.services.manga.config import MangaPipelineConfig
from src.services.manga.models import (
    AspectRatio,
    CharacterReference,
    MangaEpisodeInput,
    MangaPipelineResult,
    QualityCheckResult,
    SpeechBubble,
)
from src.services.manga.prompt_generator import MangaPromptGenerator
from src.services.manga.quality_gate import MangaQualityGate


class TestMangaPipelineConfig:
    def test_defaults(self):
        cfg = MangaPipelineConfig(api_key="x")
        assert cfg.model_id == "gemini-3.1-flash-lite-image"
        assert cfg.cost_per_image_usd == 0.034
        assert (cfg.grid_cols, cfg.grid_rows, cfg.total_panels) == (4, 6, 24)
        assert cfg.upscale_factor == 4
        assert cfg.target_upscale_width == 4096
        assert cfg.enable_typesetting is False
        assert cfg.font_size == 24

    def test_paths_coerced_to_path(self, tmp_path):
        cfg = MangaPipelineConfig(api_key="x", output_base_dir=str(tmp_path))
        assert isinstance(cfg.output_base_dir, Path)
        assert isinstance(cfg.char_ref_dir, Path)

    def test_api_key_from_gemini_env(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "from-gemini")
        assert MangaPipelineConfig().api_key == "from-gemini"

    def test_api_key_from_google_env(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_GENAI_API_KEY", "from-google")
        assert MangaPipelineConfig().api_key == "from-google"

    def test_api_key_from_nanobanana_env(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENAI_API_KEY", raising=False)
        monkeypatch.setenv("NANOBANANA_API_KEY", "from-nano")
        assert MangaPipelineConfig().api_key == "from-nano"

    def test_api_key_empty_when_unset(self, monkeypatch):
        for var in ("GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY", "NANOBANANA_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        assert MangaPipelineConfig().api_key == ""

    def test_explicit_api_key_wins(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "env-key")
        assert MangaPipelineConfig(api_key="explicit").api_key == "explicit"


class TestMangaModels:
    def test_aspect_ratios(self):
        assert AspectRatio.RATIO_3_4.value == "3:4"
        assert AspectRatio.RATIO_2_3.value == "2:3"
        assert AspectRatio.RATIO_1_1.value == "1:1"
        assert AspectRatio.RATIO_16_9.value == "16:9"

    def test_character_reference(self, tmp_path):
        ref = CharacterReference(name="Aoi", master_image_path=tmp_path / "a.png")
        assert ref.description == ""

    def test_speech_bubble_defaults(self):
        b = SpeechBubble(panel_index=3, text="やあ")
        assert (b.rel_x, b.rel_y) == (0.5, 0.5)
        assert b.bubble_type == "normal"
        assert b.speaker == ""

    def test_episode_input_defaults(self):
        ep = MangaEpisodeInput(episode_number=1, title="T", synopsis="S")
        assert ep.characters == []
        assert ep.dialogues == []
        assert ep.aspect_ratio is AspectRatio.RATIO_3_4

    def test_mutable_defaults_not_shared(self):
        a = MangaEpisodeInput(episode_number=1, title="a", synopsis="s")
        b = MangaEpisodeInput(episode_number=2, title="b", synopsis="s")
        a.characters.append("X")
        assert b.characters == []

    def test_quality_check_result_defaults(self):
        r = QualityCheckResult(
            is_valid=True, grid_score=0.9, line_sharpness_score=0.9, color_bleed_score=0.0
        )
        assert r.reasons == []

    def test_pipeline_result_defaults(self):
        r = MangaPipelineResult(episode_number=7)
        assert r.api_calls_count == 1
        assert r.estimated_cost_usd == 0.034
        assert r.typeset_applied is False
        assert r.quality_result is None
        assert r.metadata == {}


class TestMangaPromptGenerator:
    def _ep(self, **kw):
        base = dict(episode_number=3, title="夜明け", synopsis="主人公が走る。")
        base.update(kw)
        return MangaEpisodeInput(**base)

    def test_default_negative_prompt(self):
        gen = MangaPromptGenerator()
        assert gen.negative_prompt == MangaPromptGenerator.DEFAULT_NEGATIVE_PROMPT

    def test_custom_negative_prompt(self):
        gen = MangaPromptGenerator(default_negative_prompt="blurry")
        assert gen.negative_prompt == "blurry"

    def test_build_prompt_contains_core_parts(self):
        gen = MangaPromptGenerator()
        prompt = gen.build_prompt(self._ep(characters=["Aoi", "Ren"], setting="教室"))
        assert "Episode 3" in prompt
        assert "'夜明け'" in prompt
        assert "in 教室, " in prompt
        assert "starring Aoi, Ren" in prompt
        assert "4x6 grid layout" in prompt
        assert "no speech bubbles" in prompt

    def test_build_prompt_without_setting_or_characters(self):
        gen = MangaPromptGenerator()
        prompt = gen.build_prompt(self._ep())
        assert "in ," not in prompt
        assert "starring characters" in prompt

    def test_build_prompt_with_character_refs(self, tmp_path):
        gen = MangaPromptGenerator()
        refs = [
            CharacterReference(name="Aoi", master_image_path=tmp_path / "a.png"),
            CharacterReference(name="Ren", master_image_path=tmp_path / "r.png"),
        ]
        prompt = gen.build_prompt(self._ep(), refs)
        assert "maintaining strictly consistent character appearance with Aoi, Ren, " in prompt

    def test_build_negative_prompt_plain(self):
        gen = MangaPromptGenerator()
        assert gen.build_negative_prompt() == gen.negative_prompt

    def test_build_negative_prompt_with_additional(self):
        gen = MangaPromptGenerator()
        assert gen.build_negative_prompt("extra") == f"{gen.negative_prompt}, extra"


def _make_image(path: Path, size=(600, 800), color="white", mode="RGB"):
    from PIL import Image

    img = Image.new(mode, size, color=255 if color == "white" else 0)
    img.save(path, format="PNG")
    return path


class TestMangaQualityGate:
    def test_defaults(self):
        gate = MangaQualityGate()
        assert gate.min_grid_score == 0.50
        assert gate.min_sharpness_score == 0.25
        assert gate.max_color_bleed_score == 0.25

    def test_missing_file_invalid(self, tmp_path):
        res = MangaQualityGate().evaluate(tmp_path / "nope.png")
        assert res.is_valid is False
        assert res.color_bleed_score == 1.0
        assert "does not exist" in res.reasons[0]

    def test_empty_file_invalid(self, tmp_path):
        p = tmp_path / "empty.png"
        p.write_bytes(b"")
        res = MangaQualityGate().evaluate(p)
        assert res.is_valid is False

    def test_low_resolution_invalid(self, tmp_path):
        p = _make_image(tmp_path / "small.png", size=(100, 100), color="white", mode="L")
        res = MangaQualityGate().evaluate(p)
        assert res.is_valid is False
        assert res.reasons[0].startswith("Resolution too low")

    def test_grayscale_good_contrast_passes(self, tmp_path):
        from PIL import Image, ImageDraw

        p = tmp_path / "good.png"
        img = Image.new("L", (600, 800), color=255)
        d = ImageDraw.Draw(img)
        for i in range(0, 600, 7):
            d.line([(i, 0), (i, 800)], fill=0, width=3)
        img.save(p, format="PNG")

        res = MangaQualityGate().evaluate(p)
        assert res.is_valid is True
        assert res.reasons == []
        assert res.grid_score == 0.85
        assert res.line_sharpness_score > 0.25

    def test_flat_image_fails_sharpness(self, tmp_path):
        p = _make_image(tmp_path / "flat.png", size=(600, 800), color="white", mode="L")
        res = MangaQualityGate().evaluate(p)
        assert res.is_valid is False
        assert any("Sharpness" in r for r in res.reasons)

    def test_color_bleed_detected(self, tmp_path):
        from PIL import Image, ImageDraw

        p = tmp_path / "color.png"
        img = Image.new("RGB", (600, 800), color=(255, 0, 0))
        d = ImageDraw.Draw(img)
        for i in range(0, 600, 7):
            d.line([(i, 0), (i, 800)], fill=(0, 0, 255), width=3)
        img.save(p, format="PNG")

        res = MangaQualityGate().evaluate(p)
        assert res.color_bleed_score > 0.25
        assert res.is_valid is False
        assert any("Color bleed" in r for r in res.reasons)

    def test_exception_falls_back_to_valid(self, tmp_path, monkeypatch):
        import PIL.Image as ImageMod

        p = _make_image(tmp_path / "boom.png", size=(600, 800), color="white", mode="L")

        def _open(*a, **k):
            raise OSError("corrupt image")

        monkeypatch.setattr(ImageMod, "open", _open)
        res = MangaQualityGate().evaluate(p)
        assert res.is_valid is True
        assert res.grid_score == 0.7
        assert "Checked with fallback" in res.reasons[0]
