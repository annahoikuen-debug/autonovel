"""Unit tests for illustration base/prompt_builder/factory/clients/adapters."""
import base64
import io
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.services.illustration.adapters.base import (
    GeneratedImageResult,
    ImageGenerationAdapter,
    ImagePromptRequest,
)
from src.services.illustration.adapters.dalle3_adapter import Dalle3Adapter
from src.services.illustration.adapters.fal_adapter import FalAiAdapter
from src.services.illustration.adapters.mock_adapter import (
    DUMMY_PNG,
    MockImageAdapter,
)
from src.services.illustration.base import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageGeneratorClient,
    extract_png_metadata,
)
from src.services.illustration.dalle_client import DalleClient
from src.services.illustration.mock_client import MockImageClient
from src.services.illustration.prompt_builder import PromptBuilder
from src.services.illustration.prompt_generator import IllustrationPromptGenerator
from src.services.illustration.sd_client import SDWebUIClient


def _png_bytes(size=(8, 6), color=(255, 0, 0)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class TestIllustrationBase:
    def test_request_defaults(self):
        req = ImageGenerationRequest(prompt="a girl")
        assert req.negative_prompt == ""
        assert (req.width, req.height) == (512, 768)
        assert req.steps == 25
        assert req.cfg_scale == 7.0
        assert req.seed == -1
        assert req.lora_tags is None

    def test_result_defaults(self):
        res = ImageGenerationResult(image_bytes=b"x")
        assert res.format == "png"
        assert res.seed_used == -1
        assert res.metadata is None

    def test_abstract_client_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ImageGeneratorClient()

    def test_extract_png_metadata_valid(self):
        meta = extract_png_metadata(_png_bytes((12, 34)))
        assert meta["width"] == 12
        assert meta["height"] == 34
        assert meta["format"] == "PNG"
        assert meta["has_text"] is False
        assert meta["has_watermark"] is False

    def test_extract_png_metadata_invalid_bytes(self):
        meta = extract_png_metadata(b"not-a-png")
        assert meta["width"] == 0
        assert meta["height"] == 0
        assert meta["format"] is None


class TestPromptBuilder:
    def test_standard_negative_prompt(self):
        out = PromptBuilder.build_negative_prompt()
        assert "bad anatomy" in out
        assert "watermark" in out

    def test_negative_without_standard(self):
        assert PromptBuilder.build_negative_prompt(include_standard=False) == ""

    def test_negative_custom_only(self):
        out = PromptBuilder.build_negative_prompt("my_neg", include_standard=False)
        assert out == "my_neg"

    def test_negative_combined(self):
        out = PromptBuilder.build_negative_prompt("my_neg")
        assert "bad anatomy" in out
        assert out.endswith("my_neg")

    def test_positive_prompt_base_only(self):
        out = PromptBuilder.build_positive_prompt("a boy", quality_enhancement=False)
        assert out == "a boy"

    def test_positive_prompt_all_parts(self):
        out = PromptBuilder.build_positive_prompt(
            "a boy", character_additions="blue hair", custom_positive="cinematic"
        )
        assert out.startswith("a boy")
        assert "blue hair" in out
        assert "masterpiece" in out
        assert out.endswith("cinematic")

    def test_positive_prompt_empty_additions(self):
        out = PromptBuilder.build_positive_prompt("base", character_additions="")
        assert out.startswith("base, masterpiece")


class TestIllustrationPromptGenerator:
    def test_all_parts(self):
        gen = IllustrationPromptGenerator()
        out = gen.build_prompt("a girl", "happy", "anime")
        assert out == "a girl, mood: happy, style: anime"

    def test_missing_parts(self):
        gen = IllustrationPromptGenerator()
        assert gen.build_prompt("", "", "") == ""

    def test_partial(self):
        gen = IllustrationPromptGenerator()
        assert gen.build_prompt("a girl", "", "") == "a girl"


class TestMockImageClient:
    async def test_generates_real_png(self):
        client = MockImageClient(background_color="#123456")
        res = await client.generate_image(
            ImageGenerationRequest(prompt="p", width=16, height=20, seed=7)
        )
        assert res.image_bytes.startswith(b"\x89PNG")
        assert res.metadata["width"] == 16
        assert res.metadata["height"] == 20
        assert res.metadata["provider"] == "mock"
        assert res.seed_used == 7

    async def test_seed_defaults_when_negative(self):
        client = MockImageClient()
        res = await client.generate_image(ImageGenerationRequest(prompt="p", seed=-1))
        assert res.seed_used == 42

    async def test_fallback_when_pil_missing(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "PIL", None)
        client = MockImageClient()
        res = await client.generate_image(ImageGenerationRequest(prompt="p"))
        assert res.image_bytes == (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
            b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )


class TestMockImageAdapter:
    def test_provider_name(self):
        assert MockImageAdapter().provider_name == "mock"

    async def test_generate_image(self):
        req = ImagePromptRequest(prompt="a cat", aspect_ratio="16:9", style="anime")
        res = await MockImageAdapter().generate_image(req)
        assert isinstance(res, GeneratedImageResult)
        assert res.image_bytes == DUMMY_PNG
        assert res.provider == "mock"
        assert res.cost_usd == 0.0
        assert res.metadata["mock_prompt"] == "a cat"
        assert res.metadata["aspect_ratio"] == "16:9"
        assert res.metadata["style"] == "anime"


class TestAdapterBaseContract:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            ImageGenerationAdapter()

    def test_subclass_must_implement(self):
        class Incomplete(ImageGenerationAdapter):
            @property
            def provider_name(self):
                return "incomplete"

        with pytest.raises(TypeError):
            Incomplete()

    def test_request_defaults(self):
        req = ImagePromptRequest(prompt="p")
        assert (req.width, req.height) == (1024, 1024)
        assert req.aspect_ratio == "1:1"
        assert req.seed is None
        assert req.style == "anime"

    def test_result_metadata_not_shared(self):
        a = GeneratedImageResult(image_bytes=b"a")
        b = GeneratedImageResult(image_bytes=b"b")
        a.metadata["x"] = 1
        assert b.metadata == {}


class TestDalle3Adapter:
    def _mock_client(self, payload):
        client = AsyncMock()
        resp = MagicMock()
        resp.json.return_value = payload
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        return client

    def test_init_strips_trailing_slash(self):
        a = Dalle3Adapter(api_key="k", base_url="https://x/v1/")
        assert a.base_url == "https://x/v1"
        assert a._client is None

    def test_provider_name(self):
        assert Dalle3Adapter(api_key="k").provider_name == "dalle3"

    @pytest.mark.parametrize(
        "ratio,expected",
        [
            ("1:1", "1024x1024"),
            ("16:9", "1792x1024"),
            ("horizontal", "1792x1024"),
            ("9:16", "1024x1792"),
            ("vertical", "1024x1792"),
        ],
    )
    async def test_size_mapping(self, ratio, expected):
        payload = {"data": [{"b64_json": base64.b64encode(b"IMG").decode()}]}
        client = self._mock_client(payload)
        a = Dalle3Adapter(api_key="k", client=client)
        res = await a.generate_image(ImagePromptRequest(prompt="p", aspect_ratio=ratio))
        assert res.image_bytes == b"IMG"
        assert client.post.call_args.kwargs["json"]["size"] == expected

    async def test_revised_prompt_metadata(self):
        payload = {"data": [{"b64_json": "SU1H", "revised_prompt": "revised!"}]}
        client = self._mock_client(payload)
        a = Dalle3Adapter(api_key="k", client=client)
        res = await a.generate_image(ImagePromptRequest(prompt="p"))
        assert res.metadata["revised_prompt"] == "revised!"
        assert res.cost_usd == 0.040
        assert res.provider == "dalle3"
        assert res.format == "png"

    async def test_auth_header(self):
        client = self._mock_client({"data": [{"b64_json": "SU1H"}]})
        a = Dalle3Adapter(api_key="sk-abc", client=client)
        await a.generate_image(ImagePromptRequest(prompt="p"))
        assert client.post.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-abc"

    async def test_creates_own_client_when_none(self, monkeypatch):
        payload = {"data": [{"b64_json": "SU1H"}]}

        class _FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None, headers=None):
                resp = MagicMock()
                resp.json.return_value = payload
                resp.raise_for_status = MagicMock()
                return resp

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        a = Dalle3Adapter(api_key="k")
        res = await a.generate_image(ImagePromptRequest(prompt="p"))
        assert res.image_bytes == b"IMG"


class TestFalAiAdapter:
    def _mock_client(self, payload, content=b"FALPNG"):
        client = AsyncMock()
        submit = MagicMock()
        submit.json.return_value = payload
        submit.raise_for_status = MagicMock()
        img = MagicMock()
        img.content = content
        img.raise_for_status = MagicMock()
        client.post.return_value = submit
        client.get.return_value = img
        return client

    def test_init(self):
        a = FalAiAdapter(api_key="k")
        assert a.model_endpoint == "fal-ai/flux/schnell"
        assert a._client is None

    def test_provider_name(self):
        assert FalAiAdapter(api_key="k").provider_name == "fal_ai"

    @pytest.mark.parametrize(
        "ratio,expected",
        [
            ("1:1", "square_hd"),
            ("9:16", "portrait_16_9"),
            ("vertical", "portrait_16_9"),
            ("16:9", "landscape_16_9"),
            ("horizontal", "landscape_16_9"),
        ],
    )
    async def test_image_size_mapping(self, ratio, expected):
        client = self._mock_client({"images": [{"url": "https://img/x.png"}]})
        a = FalAiAdapter(api_key="k", client=client)
        await a.generate_image(ImagePromptRequest(prompt="p", aspect_ratio=ratio))
        assert client.post.call_args.kwargs["json"]["image_size"] == expected

    async def test_steps_capped_for_schnell(self):
        client = self._mock_client({"images": [{"url": "https://img/x.png"}]})
        a = FalAiAdapter(api_key="k", client=client)
        await a.generate_image(ImagePromptRequest(prompt="p", steps=50))
        assert client.post.call_args.kwargs["json"]["num_inference_steps"] == 10

    async def test_steps_uncapped_for_other_endpoints(self):
        client = self._mock_client({"images": [{"url": "https://img/x.png"}]})
        a = FalAiAdapter(api_key="k", model_endpoint="fal-ai/sdxl", client=client)
        await a.generate_image(ImagePromptRequest(prompt="p", steps=50))
        assert client.post.call_args.kwargs["json"]["num_inference_steps"] == 50

    async def test_success_returns_bytes(self):
        client = self._mock_client({"images": [{"url": "https://img/x.png"}]}, b"FALPNG")
        a = FalAiAdapter(api_key="fk", client=client)
        res = await a.generate_image(ImagePromptRequest(prompt="p", seed=99))
        assert res.image_bytes == b"FALPNG"
        assert res.provider == "fal_ai"
        assert res.cost_usd == 0.0035
        assert res.metadata["endpoint"] == "fal-ai/flux/schnell"
        assert client.post.call_args.kwargs["headers"]["Authorization"] == "Key fk"
        assert client.post.call_args.kwargs["json"]["seed"] == 99
        assert client.get.call_args.args[0] == "https://img/x.png"

    async def test_creates_own_client_when_none(self, monkeypatch):
        class _FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None, headers=None):
                resp = MagicMock()
                resp.json.return_value = {"images": [{"url": "https://img/x.png"}]}
                resp.raise_for_status = MagicMock()
                return resp

            async def get(self, url):
                resp = MagicMock()
                resp.content = b"OWN"
                resp.raise_for_status = MagicMock()
                return resp

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        a = FalAiAdapter(api_key="k")
        res = await a.generate_image(ImagePromptRequest(prompt="p"))
        assert res.image_bytes == b"OWN"


class TestDalleClient:
    async def test_base_url_normalised(self):
        c = DalleClient(base_url="https://api.openai.com/")
        assert c.base_url == "https://api.openai.com"
        assert c.max_retries == 3
        assert c.timeout == 120.0

    async def test_generate_success(self, monkeypatch):
        payload = {"data": [{"url": "https://img/a.png"}]}

        class _Resp:
            def __init__(self, content=b"DLPNG", data=None):
                self.content = content
                self._data = data

            def raise_for_status(self):
                pass

            def json(self):
                return self._data

        class _FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None, headers=None):
                return _Resp(data=payload)

            async def get(self, url):
                return _Resp(content=b"DLPNG")

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        c = DalleClient(api_key="sk-1")
        res = await c.generate_image(ImageGenerationRequest(prompt="p", seed=5))
        assert res.image_bytes == b"DLPNG"
        assert res.metadata["provider"] == "dalle3"
        assert res.metadata["url"] == "https://img/a.png"
        assert res.seed_used == 5

    async def test_retries_then_raises(self, monkeypatch):
        class _Boom:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "AsyncClient", _Boom)
        sleep_calls = []

        async def _no_sleep(sec):
            sleep_calls.append(sec)

        monkeypatch.setattr("src.services.illustration.dalle_client.asyncio.sleep", _no_sleep)
        c = DalleClient(api_key="sk-1", max_retries=3)
        with pytest.raises(RuntimeError, match="after 3 attempts"):
            await c.generate_image(ImageGenerationRequest(prompt="p"))
        assert sleep_calls == [1, 2]

    async def test_no_sleep_after_final_attempt(self, monkeypatch):
        class _Boom:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "AsyncClient", _Boom)
        c = DalleClient(api_key="sk-1", max_retries=1)
        with pytest.raises(RuntimeError, match="after 1 attempts"):
            await c.generate_image(ImageGenerationRequest(prompt="p"))


class TestSDWebUIClient:
    def _payload(self, images=("SU1H",)):
        import base64 as _b64

        return {"images": list(images)}

    def test_init(self):
        c = SDWebUIClient(base_url="http://localhost:7860/")
        assert c.base_url == "http://localhost:7860"
        assert c.max_retries == 3

    async def test_generate_success(self, monkeypatch):
        payload = {
            "images": ["SU1H"],
            "info": {"seed": 4242},
        }

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        class _FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None, headers=None):
                self.captured = json
                return _Resp()

        captured = {}

        class _Client2(_FakeClient):
            async def post(self, url, json=None, headers=None):
                captured.update(json or {})
                return _Resp()

        monkeypatch.setattr(httpx, "AsyncClient", _Client2)
        c = SDWebUIClient()
        res = await c.generate_image(
            ImageGenerationRequest(
                prompt="p", negative_prompt="neg", seed=11, lora_tags=["anime", "detail"]
            )
        )
        assert res.image_bytes == b"IMG"
        assert res.seed_used == 4242
        assert res.metadata["provider"] == "sd_webui"
        assert res.metadata["cfg_scale"] == 7.0
        assert captured["prompt"] == "p, anime, detail"
        assert captured["negative_prompt"] == "neg"
        assert captured["seed"] == 11

    async def test_seed_none_when_negative(self, monkeypatch):
        captured = {}
        payload = {"images": ["SU1H"]}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        class _FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None, headers=None):
                captured.update(json or {})
                return _Resp()

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        c = SDWebUIClient()
        res = await c.generate_image(ImageGenerationRequest(prompt="p", seed=-1))
        assert captured["seed"] is None
        assert res.seed_used == -1

    async def test_seed_falls_back_to_request(self, monkeypatch):
        payload = {"images": ["SU1H"], "info": {"seed": None}}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        class _FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None, headers=None):
                return _Resp()

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        c = SDWebUIClient()
        res = await c.generate_image(ImageGenerationRequest(prompt="p", seed=88))
        assert res.seed_used == 88

    async def test_no_images_retries_then_raises(self, monkeypatch):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"images": []}

        class _FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None, headers=None):
                return _Resp()

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        monkeypatch.setattr("src.services.illustration.sd_client.time.sleep", AsyncMock())
        c = SDWebUIClient(max_retries=2)
        with pytest.raises(RuntimeError, match="no images"):
            await c.generate_image(ImageGenerationRequest(prompt="p"))

    async def test_http_error_retries(self, monkeypatch):
        class _FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                raise httpx.HTTPError("500")

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        monkeypatch.setattr("src.services.illustration.sd_client.time.sleep", AsyncMock())
        c = SDWebUIClient(max_retries=2)
        with pytest.raises(RuntimeError, match="after 2 attempts"):
            await c.generate_image(ImageGenerationRequest(prompt="p"))


class TestImageFactories:
    def test_get_image_adapter_mock(self, monkeypatch):
        from src.services.illustration.factory import get_image_adapter

        monkeypatch.setenv("IMAGE_PROVIDER", "mock")
        assert isinstance(get_image_adapter(), MockImageAdapter)

    def test_get_image_adapter_dalle3(self, monkeypatch):
        from src.services.illustration.factory import get_image_adapter

        monkeypatch.setenv("OPENAI_API_KEY", "sk-1")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://custom/v1")
        a = get_image_adapter("dalle3")
        assert isinstance(a, Dalle3Adapter)
        assert a.api_key == "sk-1"
        assert a.base_url == "https://custom/v1"

    @pytest.mark.parametrize("name", ["dalle", "openai"])
    def test_get_image_adapter_openai_aliases(self, name, monkeypatch):
        from src.services.illustration.factory import get_image_adapter

        assert isinstance(get_image_adapter(name), Dalle3Adapter)

    def test_get_image_adapter_fal(self, monkeypatch):
        from src.services.illustration.factory import get_image_adapter

        monkeypatch.setenv("FAL_KEY", "fal-1")
        assert isinstance(get_image_adapter("fal_ai"), FalAiAdapter)

    def test_get_image_adapter_fal_alt_env(self, monkeypatch):
        from src.services.illustration.factory import get_image_adapter

        monkeypatch.delenv("FAL_KEY", raising=False)
        monkeypatch.setenv("FAL_AI_API_KEY", "fal-2")
        a = get_image_adapter("fal")
        assert a.api_key == "fal-2"

    def test_get_image_adapter_from_env(self, monkeypatch):
        from src.services.illustration.factory import get_image_adapter

        monkeypatch.setenv("IMAGE_PROVIDER", "DALLE3")
        assert isinstance(get_image_adapter(), Dalle3Adapter)

    def test_get_image_adapter_unknown_falls_back(self, monkeypatch):
        from src.services.illustration.factory import get_image_adapter

        assert isinstance(get_image_adapter("nope"), MockImageAdapter)

    def test_get_image_client_mock(self, monkeypatch):
        from src.services.illustration.factory import get_image_client

        monkeypatch.setenv("IMAGE_PROVIDER", "mock")
        assert isinstance(get_image_client(), MockImageClient)

    def test_get_image_client_sd_webui(self, monkeypatch):
        from src.services.illustration.factory import get_image_client

        monkeypatch.setenv("SD_WEBUI_URL", "http://sd:7860")
        c = get_image_client("sd_webui")
        assert isinstance(c, SDWebUIClient)
        assert c.base_url == "http://sd:7860"

    def test_get_image_client_dalle(self, monkeypatch):
        from src.services.illustration.factory import get_image_client

        monkeypatch.setenv("OPENAI_API_KEY", "sk-9")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://oai")
        c = get_image_client("dalle")
        assert isinstance(c, DalleClient)
        assert c.api_key == "sk-9"
        assert c.base_url == "https://oai"

    def test_get_image_client_comfyui_falls_back(self, monkeypatch):
        from src.services.illustration.factory import get_image_client

        assert isinstance(get_image_client("comfyui"), MockImageClient)

    def test_get_image_client_unknown_raises(self, monkeypatch):
        from src.services.illustration.factory import get_image_client

        with pytest.raises(ValueError, match="Unknown image provider"):
            get_image_client("bogus")

    def test_get_image_client_cached(self, monkeypatch):
        from src.services.illustration import factory

        monkeypatch.setattr(factory, "_cached_client", None, raising=False)
        first = factory.get_image_client_cached("mock")
        second = factory.get_image_client_cached("mock")
        assert first is second
        factory._cached_client = None
