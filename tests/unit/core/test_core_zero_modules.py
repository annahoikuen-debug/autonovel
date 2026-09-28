"""core の 0% モジュール（plugin_loader / executor_manager / llm factory）の単体テスト."""

import importlib
import json
import sys

import pytest

from src.core import executor_manager as executor_manager_module
from src.core.executor_manager import ExecutorManager
from src.core.llm.adapters.mock_unified_client import UnifiedMockLLMClient
from src.core.llm.factory import create_unified_llm_client
from src.core.plugin_loader import PluginLoader


class TestPluginLoader:
    def _redirect(self, tmp_path, monkeypatch):
        """plugin_loader.__file__ を tmp 配下（src/core/）に差し替える.

        PluginLoader は Path(__file__).parents[2] / "plugins" を使うため、
        tmp_path/src/core/plugin_loader.py を指せば tmp_path/plugins を参照する。
        """
        loader_file = tmp_path / "src" / "core" / "plugin_loader.py"
        loader_file.parent.mkdir(parents=True, exist_ok=True)
        loader_file.write_text("", encoding="utf-8")
        monkeypatch.setattr("src.core.plugin_loader.__file__", str(loader_file))
        return tmp_path / "plugins"

    def test_plugins_dir_missing(self, tmp_path, monkeypatch, caplog):
        self._redirect(tmp_path, monkeypatch)
        with caplog.at_level("WARNING"):
            PluginLoader.load_all_plugins()
        assert any("not found" in r.message for r in caplog.records)

    def test_manifest_loading(self, tmp_path, monkeypatch, caplog):
        plugins = self._redirect(tmp_path, monkeypatch)
        plugins.mkdir()
        (plugins / "manifest.json").write_text(
            json.dumps({"plugins": [{"name": "ok"}, {"name": "broken"}]}),
            encoding="utf-8",
        )
        loaded = []
        failing = []

        def fake_import(name):
            if name.endswith("broken"):
                failing.append(name)
                raise ImportError("boom")
            loaded.append(name)
            return object()

        monkeypatch.setattr(importlib, "import_module", fake_import)
        with caplog.at_level("ERROR"):
            PluginLoader.load_all_plugins()
        assert loaded == ["plugins.ok"]
        assert failing == ["plugins.broken"]
        assert any("Failed to load" in r.message for r in caplog.records)

    def test_fallback_directory_scan(self, tmp_path, monkeypatch):
        plugins = self._redirect(tmp_path, monkeypatch)
        plugins.mkdir()
        (plugins / "alpha.py").write_text("", encoding="utf-8")
        (plugins / "_private.py").write_text("", encoding="utf-8")
        (plugins / "__init__.py").write_text("", encoding="utf-8")

        loaded = []
        monkeypatch.setattr(importlib, "import_module", lambda n: loaded.append(n))
        monkeypatch.setattr(sys, "path", list(sys.path))
        PluginLoader.load_all_plugins()
        assert loaded == ["plugins.alpha"]
        assert str(tmp_path) in sys.path

    def test_fallback_directory_scan_error(self, tmp_path, monkeypatch, caplog):
        plugins = self._redirect(tmp_path, monkeypatch)
        plugins.mkdir()
        (plugins / "alpha.py").write_text("", encoding="utf-8")

        def boom(name):
            raise ImportError("nope")

        monkeypatch.setattr(importlib, "import_module", boom)
        with caplog.at_level("ERROR"):
            PluginLoader.load_all_plugins()
        assert any("Failed to load plugin" in r.message for r in caplog.records)

    def test_outer_exception(self, monkeypatch, caplog):
        import pathlib

        real_path = pathlib.Path

        def boom(*args, **kwargs):
            raise OSError("disk")

        monkeypatch.setattr("src.core.plugin_loader.pathlib.Path", boom)
        with caplog.at_level("ERROR"):
            PluginLoader.load_all_plugins()
        assert any("Error in load_all_plugins" in r.message for r in caplog.records)
        monkeypatch.setattr("src.core.plugin_loader.pathlib.Path", real_path)


class TestExecutorManager:
    async def test_singleton(self):
        assert ExecutorManager() is ExecutorManager()

    async def test_run_io(self):
        mgr = ExecutorManager()
        assert await mgr.run_io(lambda a, b: a + b, 1, 2) == 3

    async def test_run_cpu(self):
        mgr = ExecutorManager()
        assert await mgr.run_cpu(lambda x: x * 2, 21) == 42

    async def test_run_with_kwargs(self):
        mgr = ExecutorManager()
        assert await mgr.run_io(lambda *, v: v + 1, v=1) == 2

    def test_module_level_instance(self):
        assert isinstance(executor_manager_module.executor_manager, ExecutorManager)

    def test_shutdown_uses_executors(self, monkeypatch):
        calls = []
        mgr = ExecutorManager()
        monkeypatch.setattr(mgr.io_executor, "shutdown", lambda **kw: calls.append("io"))
        monkeypatch.setattr(mgr.cpu_executor, "shutdown", lambda **kw: calls.append("cpu"))
        mgr.shutdown()
        assert calls == ["io", "cpu"]


class TestLLMFactory:
    def test_create_mock_client(self):
        client = create_unified_llm_client("mock")
        assert isinstance(client, UnifiedMockLLMClient)

    def test_create_mock_client_with_kwargs(self):
        client = create_unified_llm_client("mock", response_text="hello")
        assert isinstance(client, UnifiedMockLLMClient)

    def test_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            create_unified_llm_client("nope")


class TestExceptionsForwarding:
    def test_base_exceptions_exported(self):
        import src.core.exceptions as exc

        assert hasattr(exc, "HegemonyError")
        assert hasattr(exc, "AppError")

