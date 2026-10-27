"""src/cli/main.py および illustration_cli.py の実行経路テスト。"""
from __future__ import annotations

import sys
import types

import pytest

from src.cli import illustration_cli as icli
from src.cli.main import (
    build_parser,
    cmd_balance,
    cmd_check_env,
    cmd_export,
    cmd_init_db,
    cmd_plugins,
    main,
)


def _ns(**kw):
    import argparse

    return argparse.Namespace(**kw)


class TestCmdBalance:
    def test_unknown_type(self, capsys):
        assert cmd_balance(_ns(type="nope")) == 1
        assert "Unknown balancer type" in capsys.readouterr().err

    def test_import_error(self, capsys, monkeypatch):
        # 存在しないモジュールを注入して ImportError を起こす
        monkeypatch.setitem(sys.modules, "src.narrative_balancer.dsp_balancer", None)
        assert cmd_balance(_ns(type="dsp")) == 1
        assert "not available" in capsys.readouterr().err

    @pytest.mark.parametrize("kind,modname", [
        ("dsp", "src.narrative_balancer.dsp_balancer"),
        ("csp", "src.narrative_balancer.csp_balancer"),
        ("grammar", "src.narrative_balancer.grammar_balancer"),
    ])
    def test_each_type_runs(self, capsys, monkeypatch, kind, modname):
        created = {}

        class FakeBalancer:
            def run(self):
                created["ran"] = True
                return "R"

        module = types.ModuleType(modname)
        module.__dict__[kind.capitalize() + "Balancer"] = lambda: FakeBalancer()
        monkeypatch.setitem(sys.modules, modname, module)
        assert cmd_balance(_ns(type=kind)) == 0
        assert created.get("ran")
        assert f"[balance:{kind}]" in capsys.readouterr().out

    def test_balancer_without_run(self, capsys, monkeypatch):
        class NoRun:
            pass

        module = types.ModuleType("src.narrative_balancer.dsp_balancer")
        module.DspBalancer = NoRun
        monkeypatch.setitem(sys.modules, "src.narrative_balancer.dsp_balancer", module)
        assert cmd_balance(_ns(type="dsp")) == 0
        assert "completed: None" in capsys.readouterr().out


class TestCmdExport:
    def test_import_error(self, capsys, monkeypatch):
        monkeypatch.setitem(sys.modules, "src.services.export_service", None)
        assert cmd_export(_ns(book_id=1, format="zip")) == 1
        assert "Export module not available" in capsys.readouterr().err

    def test_service_without_export(self, capsys, monkeypatch):
        module = types.ModuleType("src.services.export_service")

        class ExportService:
            pass

        module.ExportService = ExportService
        monkeypatch.setitem(sys.modules, "src.services.export_service", module)
        assert cmd_export(_ns(book_id=3, format="epub")) == 0
        out = capsys.readouterr().out
        assert "[export] completed" in out and "'book_id': 3" in out

    def test_service_with_export(self, capsys, monkeypatch):
        module = types.ModuleType("src.services.export_service")

        class ExportService:
            def export(self, book_id, fmt):
                assert book_id == 5 and fmt == "txt"
                return "E"

        module.ExportService = ExportService
        monkeypatch.setitem(sys.modules, "src.services.export_service", module)
        assert cmd_export(_ns(book_id=5, format="txt")) == 0
        assert "completed: E" in capsys.readouterr().out

    def test_service_raises(self, capsys, monkeypatch):
        module = types.ModuleType("src.services.export_service")

        class ExportService:
            def __init__(self):
                raise RuntimeError("boom")

        module.ExportService = ExportService
        monkeypatch.setitem(sys.modules, "src.services.export_service", module)
        assert cmd_export(_ns(book_id=1, format="zip")) == 1
        assert "Export failed" in capsys.readouterr().err


class TestCmdInitDb:
    def test_success(self, monkeypatch):
        script = types.ModuleType("scripts.init_db")
        script.run_migrations = lambda: True
        monkeypatch.setitem(sys.modules, "scripts.init_db", script)
        assert cmd_init_db(_ns()) == 0

    def test_failure(self, monkeypatch):
        script = types.ModuleType("scripts.init_db")
        script.run_migrations = lambda: False
        monkeypatch.setitem(sys.modules, "scripts.init_db", script)
        assert cmd_init_db(_ns()) == 1


class TestCmdCheckEnv:
    def test_json_flag(self, monkeypatch):
        script = types.ModuleType("scripts.check_env")
        seen = {}

        def main(argv):
            seen["argv"] = argv
            return 0

        script.main = main
        monkeypatch.setitem(sys.modules, "scripts.check_env", script)
        assert cmd_check_env(_ns(json=True)) == 0
        assert seen["argv"] == ["--json"]

    def test_plain(self, monkeypatch):
        script = types.ModuleType("scripts.check_env")
        seen = {}

        def main(argv):
            seen["argv"] = argv
            return 1

        script.main = main
        monkeypatch.setitem(sys.modules, "scripts.check_env", script)
        assert cmd_check_env(_ns(json=False)) == 1
        assert seen["argv"] == []


class TestCmdPlugins:
    def _registry(self, monkeypatch, entries, load_results=None):
        class Entry:
            def __init__(self, name, enabled, loaded):
                self.name = name
                self.enabled = enabled
                self.loaded = loaded

        class Registry:
            def list_plugins(self):
                return entries

            def load_all(self):
                return load_results or {}

        module = types.ModuleType("src.core.plugin_registry")
        module.get_plugin_registry = lambda: Registry()
        monkeypatch.setitem(sys.modules, "src.core.plugin_registry", module)

    def test_list(self, capsys, monkeypatch):
        self._registry(monkeypatch, [_E("a", True, False), _E("b", False, True)])
        assert cmd_plugins(_ns(load=False)) == 0
        out = capsys.readouterr().out
        assert "NAME" in out and "a" in out and "b" in out

    def test_load(self, capsys, monkeypatch):
        self._registry(monkeypatch, [_E("a", True, False)], {"a": True, "b": False})
        assert cmd_plugins(_ns(load=True)) == 0
        out = capsys.readouterr().out
        assert "[load] a: OK" in out and "[load] b: FAILED" in out


def _E(name, enabled, loaded):
    class Entry:
        pass

    e = Entry()
    e.name, e.enabled, e.loaded = name, enabled, loaded
    return e


class _FakeParser:
    def __init__(self, ns):
        self._ns = ns

    def parse_args(self, argv):
        return self._ns

    def print_help(self):
        pass


class TestMainDispatch:
    def test_no_subcommand_prints_help(self, capsys):
        assert main([]) == 0
        assert "autonovel" in capsys.readouterr().out

    def test_keyboard_interrupt(self, monkeypatch, capsys):
        def boom(_args):
            raise KeyboardInterrupt

        import argparse

        ns = argparse.Namespace(version=False, func=boom)
        import src.cli.main as climain

        monkeypatch.setattr(climain, "build_parser", lambda: _FakeParser(ns))
        assert main([]) == 130
        assert "interrupted" in capsys.readouterr().err

    def test_export_flag_required(self):
        with pytest.raises(SystemExit):
            main(["export"])

    def test_format_choices(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["export", "-b", "1", "-f", "pdf"])


class TestIllustrationCliHelpers:
    def test_model(self):
        from src.models.illustration import IllustrationModel

        assert icli._model("fast") is IllustrationModel.FAST

    def test_safety(self):
        from src.models.illustration import SafetyLevel

        assert icli._safety("r15") is SafetyLevel.R15_CONTENT
        assert icli._safety("standard") is SafetyLevel.BLOCK_SOME

    def test_read_stdin_tty(self, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        assert icli._read_stdin() == ""

    def test_read_stdin_not_tty(self, monkeypatch):
        import io

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
        assert icli._read_stdin() == "hello"

    def test_print_result_failure(self, capsys):
        with pytest.raises(SystemExit) as exc:
            icli._print_result({"status": "error", "message": "nope"})
        assert exc.value.code == 1
        assert "FAILED: nope" in capsys.readouterr().err

    def test_print_result_success(self, capsys):
        class R:
            image_url = "http://img"
            prompt = "p"

        icli._print_result({"status": "success", "result": R()})
        assert "http://img" in capsys.readouterr().out

    def test_build_agent_missing_key(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            icli._build_agent()
        assert exc.value.code == 1

    def test_build_agent_ok(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "k")
        agent = icli._build_agent()
        assert agent is not None
