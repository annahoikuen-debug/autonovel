"""プラグイン実装（social_posting / audio / multimedia）の追加テスト。"""
from __future__ import annotations

import sys
import types


from src.interfaces.plugin import BasePlugin, PluginProtocol
from src.plugins.audio.plugin import AudioPlugin
from src.plugins.multimedia.plugin import MultimediaPlugin
from src.plugins.social_posting.plugin import SocialPostingPlugin


class TestBasePlugin:
    def test_defaults(self):
        p = BasePlugin()
        assert p.name == "base"
        assert p.config == {}
        assert p.is_available() is False
        assert p.initialize() is True
        assert p.is_available() is True
        p.shutdown()
        assert p.is_available() is False

    def test_config_passthrough(self):
        p = BasePlugin(a=1, b="x")
        assert p.config == {"a": 1, "b": "x"}

    def test_satisfies_protocol(self):
        assert isinstance(BasePlugin(), PluginProtocol)


class TestSocialPostingPlugin:
    def test_satisfies_protocol(self):
        assert isinstance(SocialPostingPlugin(), PluginProtocol)

    def test_name(self):
        assert SocialPostingPlugin.name == "social_posting"

    def test_disabled_without_credentials(self):
        p = SocialPostingPlugin()
        assert p.initialize() is False
        assert p.is_available() is False

    def test_enabled_with_narou_cookie(self):
        p = SocialPostingPlugin(narou_cookie="c")
        assert p.initialize() is True
        assert p.is_available() is True
        p.shutdown()
        assert p.is_available() is False

    def test_enabled_with_kakuyomu_cookie(self):
        p = SocialPostingPlugin(kakuyomu_cookie="c")
        assert p.initialize() is True

    def test_is_available_before_init(self):
        assert SocialPostingPlugin(narou_cookie="c").is_available() is False


class TestAudioPlugin:
    def test_get_provider_before_init(self):
        assert AudioPlugin().get_provider() is None

    def test_initialize_and_shutdown(self, monkeypatch):
        created = {}

        class FakeProvider:
            def __init__(self, base_url, speaker, fallback_mode):
                created.update(base_url=base_url, speaker=speaker, fallback_mode=fallback_mode)

        module = types.ModuleType("src.plugins.audio.voicevox")
        module.VoicevoxProvider = FakeProvider
        monkeypatch.setitem(sys.modules, "src.plugins.audio.voicevox", module)

        p = AudioPlugin(voicevox_url="http://v", speaker=3, fallback_mode="stub")
        assert p.initialize() is True
        assert p.is_available() is True
        assert p.get_provider() is not None
        assert created == {"base_url": "http://v", "speaker": 3, "fallback_mode": "stub"}
        p.shutdown()
        assert p.is_available() is False
        assert p.get_provider() is None

    def test_initialize_defaults(self, monkeypatch):
        seen = {}

        class FakeProvider:
            def __init__(self, base_url, speaker, fallback_mode):
                seen.update(base_url=base_url, speaker=speaker, fallback_mode=fallback_mode)

        module = types.ModuleType("src.plugins.audio.voicevox")
        module.VoicevoxProvider = FakeProvider
        monkeypatch.setitem(sys.modules, "src.plugins.audio.voicevox", module)
        p = AudioPlugin()
        p.initialize()
        assert seen == {"base_url": None, "speaker": 1, "fallback_mode": "skip"}

    def test_initialize_import_failure(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "src.plugins.audio.voicevox", None)
        p = AudioPlugin()
        assert p.initialize() is False
        assert p.is_available() is False


class TestMultimediaPlugin:
    def test_initialize_import_failure(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "src.backend.multimedia_service", None)
        p = MultimediaPlugin()
        assert p.initialize() is False
        assert p.is_available() is False
        assert p.get_service_class() is None

    def test_initialize_success_and_shutdown(self, monkeypatch):
        class FakeService:
            pass

        module = types.ModuleType("src.backend.multimedia_service")
        module.MultimediaService = FakeService
        monkeypatch.setitem(sys.modules, "src.backend.multimedia_service", module)
        p = MultimediaPlugin()
        assert p.initialize() is True
        assert p.get_service_class() is FakeService
        p.shutdown()
        assert p.get_service_class() is None
