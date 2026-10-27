"""Unit tests for src/services/manga/{client,upscaler,typesetter,pipeline}."""
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.services.manga.client import NanoBananaClient
from src.services.manga.config import MangaPipelineConfig
from src.services.manga.models import (
    AspectRatio,
    MangaEpisodeInput,
    SpeechBubble,
)
from src.services.manga.pipeline import MangaPipeline
from src.services.manga.typesetter import MangaTypesetter
from src.services.manga.upscaler import MangaUpscaler


def _cfg(tmp_path, **kw):
    kw.setdefault("api_key", "test-key")
    return MangaPipelineConfig(output_base_dir=tmp_path, **kw)


class TestNanoBananaClientMock:
    def test_mock_mode_when_flagged(self, tmp_path):
        c = NanoBananaClient(config=_cfg(tmp_path), mock_mode=True)
        assert c.mock_mode is True
        assert c.client is None

    def test_mock_mode_when_no_api_key(self, tmp_path, monkeypatch):
        for var in ("GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY", "NANOBANANA_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        cfg = MangaPipelineConfig(output_base_dir=tmp_path, api_key="")
        c = NanoBananaClient(config=cfg)
        assert c.mock_mode is True

    def test_generate_sheet_creates_file(self, tmp_path):
        c = NanoBananaClient(config=_cfg(tmp_path), mock_mode=True)
        out = tmp_path / "raw" / "sheet.png"
        res = c.generate_sheet(prompt="p", output_path=out)
        assert res == out
        assert out.exists()
        assert out.read_bytes().startswith(b"\x89PNG")

    def test_generate_sheet_default_path(self, tmp_path):
        c = NanoBananaClient(config=_cfg(tmp_path), mock_mode=True)
        res = c.generate_sheet(prompt="p")
        assert res.parent.name == "raw_sheets"
        assert res.name.startswith("sheet_")

    def test_generate_sheet_sheet_dimensions(self, tmp_path):
        from PIL import Image

        c = NanoBananaClient(config=_cfg(tmp_path), mock_mode=True)
        out = c.generate_sheet(prompt="p", aspect_ratio="3:4", output_path=tmp_path / "a.png")
        assert Image.open(out).size == (768, 1024)

        out2 = c.generate_sheet(prompt="p", aspect_ratio="1:1", output_path=tmp_path / "b.png")
        assert Image.open(out2).size == (1024, 1024)

    def test_generate_sheet_grid_panels_drawn(self, tmp_path):
        from PIL import Image

        c = NanoBananaClient(config=_cfg(tmp_path), mock_mode=True)
        out = c.generate_sheet(prompt="p", output_path=tmp_path / "a.png")
        img = Image.open(out)
        # black panel borders present on a white background
        assert img.getextrema()[0] == 0

    def test_generate_mock_sheet_without_pil(self, tmp_path, monkeypatch):
        c = NanoBananaClient(config=_cfg(tmp_path), mock_mode=True)
        out = tmp_path / "placeholder.png"
        monkeypatch.setitem(sys.modules, "PIL.Image", None)
        monkeypatch.setitem(sys.modules, "PIL", None)
        c._generate_mock_sheet(out)
        data = out.read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n")

    def test_edit_sheet_copies_source(self, tmp_path):
        c = NanoBananaClient(config=_cfg(tmp_path), mock_mode=True)
        src = tmp_path / "src.png"
        src.write_bytes(b"original-bytes")
        out = c.edit_sheet_panel(src, "fix panel 3", output_path=tmp_path / "e.png")
        assert out.read_bytes() == b"original-bytes"

    def test_edit_sheet_generates_when_missing(self, tmp_path):
        c = NanoBananaClient(config=_cfg(tmp_path), mock_mode=True)
        out = c.edit_sheet_panel(
            tmp_path / "missing.png", "fix", output_path=tmp_path / "e.png"
        )
        assert out.exists()

    def test_edit_sheet_default_path(self, tmp_path):
        c = NanoBananaClient(config=_cfg(tmp_path), mock_mode=True)
        src = tmp_path / "src.png"
        src.write_bytes(b"x")
        out = c.edit_sheet_panel(src, "fix")
        assert out.parent.name == "edited"


class TestNanoBananaClientLive:
    def test_live_generate_sheet(self, tmp_path, monkeypatch):
        fake_types = types.ModuleType("google.genai.types")
        fake_types.GenerateImagesConfig = lambda **kw: kw
        fake_genai = types.ModuleType("google.genai")
        fake_genai.types = fake_types
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai

        fake_client = MagicMock()
        fake_client.models.generate_images.return_value = MagicMock(
            generated_images=[MagicMock(image=MagicMock(image_bytes=b"PNGBYTES"))]
        )
        fake_genai.Client = lambda **kw: fake_client

        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
        monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)

        c = NanoBananaClient(config=_cfg(tmp_path, api_key="live-key"))
        assert c.mock_mode is False
        out = c.generate_sheet(
            prompt="p", negative_prompt="bad", output_path=tmp_path / "o.png"
        )
        assert out.read_bytes() == b"PNGBYTES"
        kwargs = fake_client.models.generate_images.call_args.kwargs
        assert kwargs["config"]["negative_prompt"] == "bad"
        assert kwargs["model"] == "gemini-3.1-flash-lite-image"

    def test_live_no_negative_prompt(self, tmp_path, monkeypatch):
        fake_types = types.ModuleType("google.genai.types")
        fake_types.GenerateImagesConfig = lambda **kw: kw
        fake_genai = types.ModuleType("google.genai")
        fake_genai.types = fake_types
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai
        fake_client = MagicMock()
        fake_client.models.generate_images.return_value = MagicMock(
            generated_images=[MagicMock(image=MagicMock(image_bytes=b"B"))]
        )
        fake_genai.Client = lambda **kw: fake_client
        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
        monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)

        c = NanoBananaClient(config=_cfg(tmp_path, api_key="live-key"))
        c.generate_sheet(prompt="p", output_path=tmp_path / "o.png")
        kwargs = fake_client.models.generate_images.call_args.kwargs
        assert "negative_prompt" not in kwargs["config"]

    def test_live_no_images_raises(self, tmp_path, monkeypatch):
        fake_types = types.ModuleType("google.genai.types")
        fake_types.GenerateImagesConfig = lambda **kw: kw
        fake_genai = types.ModuleType("google.genai")
        fake_genai.types = fake_types
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai
        fake_client = MagicMock()
        fake_client.models.generate_images.return_value = MagicMock(generated_images=[])
        fake_genai.Client = lambda **kw: fake_client
        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
        monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)

        c = NanoBananaClient(config=_cfg(tmp_path, api_key="live-key"))
        with pytest.raises(RuntimeError, match="No images returned"):
            c.generate_sheet(prompt="p", output_path=tmp_path / "o.png")

    def test_api_failure_propagates(self, tmp_path, monkeypatch):
        fake_types = types.ModuleType("google.genai.types")
        fake_types.GenerateImagesConfig = lambda **kw: kw
        fake_genai = types.ModuleType("google.genai")
        fake_genai.types = fake_types
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai
        fake_client = MagicMock()
        fake_client.models.generate_images.side_effect = ValueError("api down")
        fake_genai.Client = lambda **kw: fake_client
        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
        monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)

        c = NanoBananaClient(config=_cfg(tmp_path, api_key="live-key"))
        with pytest.raises(ValueError, match="api down"):
            c.generate_sheet(prompt="p", output_path=tmp_path / "o.png")

    def test_genai_init_failure_falls_back_to_mock(self, tmp_path, monkeypatch):
        fake_genai = types.ModuleType("google.genai")

        def _boom(**kw):
            raise RuntimeError("no sdk")

        fake_genai.Client = _boom
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai
        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

        c = NanoBananaClient(config=_cfg(tmp_path, api_key="live-key"))
        assert c.mock_mode is True

    def test_live_edit_raises_not_implemented(self, tmp_path, monkeypatch):
        c = NanoBananaClient(config=_cfg(tmp_path), mock_mode=False)
        c.mock_mode = False
        with pytest.raises(NotImplementedError):
            c.edit_sheet_panel(tmp_path / "a.png", "x", output_path=tmp_path / "b.png")


class TestMangaUpscaler:
    def _src(self, tmp_path):
        from PIL import Image

        p = tmp_path / "src.png"
        Image.new("L", (64, 64), color=255).save(p, format="PNG")
        return p

    def test_defaults(self, monkeypatch):
        import src.services.manga.upscaler as mod

        monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/realesrgan")
        u = MangaUpscaler()
        assert u.scale_factor == 4
        assert u.target_width == 4096
        assert u.executable_path == "/usr/bin/realesrgan"

    def test_pil_fallback_upscales(self, tmp_path):
        src = self._src(tmp_path)
        u = MangaUpscaler(scale_factor=2, target_width=200)
        out = u.upscale(src, output_image_path=tmp_path / "up" / "o.png")
        from PIL import Image

        assert Image.open(out).size[0] == 200

    def test_default_output_path(self, tmp_path):
        src = self._src(tmp_path)
        u = MangaUpscaler(scale_factor=1, target_width=64)
        out = u.upscale(src)
        assert out.parent.name == "upscaled"
        assert out.name == "upscaled_src.png"

    def test_external_binary_success(self, tmp_path, monkeypatch):
        src = self._src(tmp_path)
        exe = tmp_path / "realesrgan"
        exe.write_text("#!/bin/sh")
        out = tmp_path / "o.png"

        u = MangaUpscaler(scale_factor=2, target_width=128, executable_path=str(exe))

        def _fake_run(cmd, capture_output, timeout):
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"EXTERNAL")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        monkeypatch.setattr("src.services.manga.upscaler.subprocess.run", _fake_run)
        assert u._run_external_realesrgan(src, out) is True
        assert out.read_bytes() == b"EXTERNAL"

    def test_external_binary_failure_returns_false(self, tmp_path):
        src = self._src(tmp_path)
        exe = tmp_path / "realesrgan"
        exe.write_text("#!/bin/sh")
        out = tmp_path / "o.png"
        u = MangaUpscaler(executable_path=str(exe))
        assert u._run_external_realesrgan(src, out) is False

    def test_external_binary_exception_logged(self, tmp_path):
        src = self._src(tmp_path)
        out = tmp_path / "o.png"
        u = MangaUpscaler(executable_path=str(tmp_path / "realesrgan"))
        # subprocess.run with a bogus exe raises -> caught
        assert u._run_external_realesrgan(src, out) is False

    def test_upscale_prefers_external(self, tmp_path, monkeypatch):
        src = self._src(tmp_path)
        exe = tmp_path / "realesrgan"
        exe.write_text("#!/bin/sh")
        out = tmp_path / "o.png"
        u = MangaUpscaler(scale_factor=2, target_width=128, executable_path=str(exe))
        called = {}

        def _fake(inp, o):
            called["used"] = True
            o.write_bytes(b"EXT")
            return True

        monkeypatch.setattr(u, "_run_external_realesrgan", _fake)
        res = u.upscale(src, output_image_path=out)
        assert called["used"] is True
        assert res.read_bytes() == b"EXT"

    def test_upscale_falls_back_when_external_fails(self, tmp_path, monkeypatch):
        src = self._src(tmp_path)
        exe = tmp_path / "realesrgan"
        exe.write_text("#!/bin/sh")
        out = tmp_path / "o.png"
        u = MangaUpscaler(scale_factor=2, target_width=128, executable_path=str(exe))
        monkeypatch.setattr(u, "_run_external_realesrgan", lambda i, o: False)
        res = u.upscale(src, output_image_path=out)
        from PIL import Image

        assert Image.open(res).size[0] == 128


class TestMangaTypesetter:
    def _img(self, tmp_path):
        from PIL import Image

        p = tmp_path / "raw" / "sheets" / "sheet.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (800, 1200), color=(255, 255, 255)).save(p, format="PNG")
        return p

    def test_default_config_used(self):
        ts = MangaTypesetter()
        assert isinstance(ts.config, MangaPipelineConfig)

    def test_no_dialogues_copies(self, tmp_path):
        src = self._img(tmp_path)
        ts = MangaTypesetter()
        out = ts.apply_typesetting(src, [], output_path=tmp_path / "fin" / "t.png")
        assert out.read_bytes() == src.read_bytes()

    def test_default_output_path(self, tmp_path):
        src = self._img(tmp_path)
        ts = MangaTypesetter()
        out = ts.apply_typesetting(src, [])
        assert out.parent.name == "finalized"
        assert out.name == "typeset_sheet.png"

    def test_typesets_bubbles(self, tmp_path):
        from PIL import Image

        src = self._img(tmp_path)
        ts = MangaTypesetter()
        bubbles = [
            SpeechBubble(panel_index=0, text="おはよう", rel_x=0.5, rel_y=0.2),
            SpeechBubble(panel_index=5, text="しね", rel_x=0.3, rel_y=0.8, bubble_type="shout"),
        ]
        out = ts.apply_typesetting(src, bubbles, output_path=tmp_path / "fin" / "t.png")
        assert out.exists()
        assert Image.open(out).mode == "RGB"

    def test_out_of_range_panels_skipped(self, tmp_path):
        src = self._img(tmp_path)
        ts = MangaTypesetter()
        bubbles = [
            SpeechBubble(panel_index=-1, text="neg"),
            SpeechBubble(panel_index=99, text="over"),
            SpeechBubble(panel_index=1, text="ok"),
        ]
        out = ts.apply_typesetting(src, bubbles, output_path=tmp_path / "fin" / "t.png")
        assert out.exists()

    def test_load_font_returns_object(self, tmp_path):
        ts = MangaTypesetter(MangaPipelineConfig(api_key="x"))
        font = ts._load_font(16)
        assert font is not None

    def test_load_font_default_when_none_available(self, tmp_path, monkeypatch):
        import PIL.ImageFont as ImageFontMod

        candidates = {
            "msgothic.ttc",
            "meiryo.ttc",
            "yumin.ttf",
            "Arial.ttf",
        }

        real_truetype = ImageFontMod.truetype

        def _maybe_fail(path, *a, **k):
            if str(path) in candidates:
                raise OSError("no font")
            return real_truetype(path, *a, **k)

        monkeypatch.setattr(ImageFontMod, "truetype", _maybe_fail)
        ts = MangaTypesetter(MangaPipelineConfig(api_key="x"))
        assert ts._load_font(12) is not None


class TestMangaPipeline:
    def _ep(self, **kw):
        base = dict(episode_number=1, title="タイトル", synopsis="あらすじ")
        base.update(kw)
        return MangaEpisodeInput(**base)

    def test_run_episode_mock(self, tmp_path):
        cfg = _cfg(tmp_path)
        pipe = MangaPipeline(config=cfg, mock_mode=True)
        res = pipe.run_episode(self._ep())
        assert res.episode_number == 1
        assert res.api_calls_count == 1
        assert res.raw_sheet_path.exists()
        assert res.upscaled_sheet_path.exists()
        assert res.final_output_path == res.upscaled_sheet_path
        assert res.typeset_applied is False
        assert res.metadata["title"] == "タイトル"
        assert res.metadata["aspect_ratio"] == "3:4"
        assert res.estimated_cost_usd == pytest.approx(0.034)

    def test_run_episode_with_typesetting(self, tmp_path):
        cfg = _cfg(tmp_path, enable_typesetting=True)
        pipe = MangaPipeline(config=cfg, mock_mode=True)
        ep = self._ep(dialogues=[SpeechBubble(panel_index=2, text="やあ")])
        res = pipe.run_episode(ep)
        assert res.typeset_applied is True
        assert res.final_output_path.name == "ep_1_final.png"
        assert res.final_output_path.exists()

    def test_typesetting_disabled_explicitly(self, tmp_path):
        cfg = _cfg(tmp_path, enable_typesetting=True)
        pipe = MangaPipeline(config=cfg, mock_mode=True)
        ep = self._ep(dialogues=[SpeechBubble(panel_index=2, text="やあ")])
        res = pipe.run_episode(ep, enable_typesetting=False)
        assert res.typeset_applied is False

    def test_typesetting_without_dialogues(self, tmp_path):
        cfg = _cfg(tmp_path, enable_typesetting=True)
        pipe = MangaPipeline(config=cfg, mock_mode=True)
        res = pipe.run_episode(self._ep())
        assert res.typeset_applied is False

    def test_retries_on_quality_failure(self, tmp_path, monkeypatch):
        cfg = _cfg(tmp_path)
        pipe = MangaPipeline(config=cfg, mock_mode=True)

        results = iter(
            [
                type("R", (), {"is_valid": False, "reasons": ["bad"]})(),
                type("R", (), {"is_valid": True, "reasons": []})(),
            ]
        )
        monkeypatch.setattr(pipe.quality_gate, "evaluate", lambda p: next(results))
        res = pipe.run_episode(self._ep(), max_retries=2)
        assert res.api_calls_count == 2
        assert res.quality_result.is_valid is True

    def test_exhausted_retries(self, tmp_path, monkeypatch):
        cfg = _cfg(tmp_path)
        pipe = MangaPipeline(config=cfg, mock_mode=True)
        monkeypatch.setattr(
            pipe.quality_gate,
            "evaluate",
            lambda p: type("R", (), {"is_valid": False, "reasons": ["bad"]})(),
        )
        res = pipe.run_episode(self._ep(), max_retries=1)
        assert res.api_calls_count == 2
        assert res.quality_result.is_valid is False

    def test_run_episode_uses_aspect_ratio(self, tmp_path):
        cfg = _cfg(tmp_path)
        pipe = MangaPipeline(config=cfg, mock_mode=True)
        ep = self._ep(aspect_ratio=AspectRatio.RATIO_1_1)
        res = pipe.run_episode(ep)
        assert res.metadata["aspect_ratio"] == "1:1"
